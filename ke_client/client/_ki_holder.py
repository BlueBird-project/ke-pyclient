import inspect
import logging.config
from functools import wraps
from typing import Union, Callable, Optional, List, Dict, Any, get_args, get_origin, \
    Iterable, Tuple, TypeAlias

from ke_client.client._ke_request_client import KERequestClient
from ke_client.client._ki_bindings import BindingsBase
from ke_client.client._ki_exceptions import KIError, KITypeError

from ke_client.client._ki_utils import verify_in_bindings_ki, verify_out_bindings_ki, _verify_required_bindings, \
    prepare_ke_request
from ke_client.ki_model import KnowledgeInteractionType, KIPostResponse, KIAskResponse, KnowledgeInteraction

KIBindings: TypeAlias = List[Union[Dict[str, Any], BindingsBase]]


# region helpers
def _verify_mismatched_bindings(ki_id: str, input_bindings, output_bindings):
    """
    verify if input bindings values match the output
    :param ki_id:
    :param input_bindings:
    :param output_bindings:
    :return:
    """

    def _keys(ki_binding: Union[BindingsBase, dict]) -> Iterable[str]:
        if type(ki_binding) is dict:
            ki_binding: dict
            return ki_binding.keys()
        if issubclass(type(ki_binding), BindingsBase):
            return ki_binding.n3().keys()
        raise KITypeError(f"Invalid type bindings type: {type(ki_binding)} ", ctx="verify_mismatched_bindings:_keys")

    def _items(ki_binding: Union[BindingsBase, dict]) -> Iterable[Tuple[str, str]]:
        if type(ki_binding) is dict:
            return ki_binding.items()
        if issubclass(type(ki_binding), BindingsBase):
            return ki_binding.n3().items()
        raise KITypeError(f"Invalid type bindings type: {type(ki_binding)} ", ctx="verify_mismatched_bindings:_items")

    input_keys = {k for ib in input_bindings for k in _keys(ib)}
    pair_set = {f"{k}_{v}" for ib in input_bindings for k, v in _items(ib)}
    err_set = {f"{k}:{v}" for ab in output_bindings for k, v in _items(ab) if
               k in input_keys and f"{k}_{v}" not in pair_set}
    if len(err_set) > 0:
        raise Exception(
            f"input bindings don't match output bindings for:{ki_id} =  {err_set}")


def _init_ki_kwargs(wrapper_args, params: Dict[str, inspect.Parameter]):
    _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
               k in params}
    bindings_annotation = get_origin(params["bindings"].annotation)
    if "bindings" in _kwargs and (bindings_annotation is not None) and issubclass(bindings_annotation, list):
        # if "bindings" in _kwargs and issubclass(params["bindings"].annotation, BindingsBase):
        cls_annotations = get_args(params["bindings"].annotation)
        if len(cls_annotations) == 1 and issubclass(cls_annotations[0], BindingsBase):
            _kwargs["bindings"] = [cls_annotations[0](**b) for b in _kwargs["bindings"]]
    return _kwargs


# endregion

class KIHolder:
    _client_ki: Dict[str, KnowledgeInteraction]
    _ke_client: Optional[KERequestClient]
    _kb_id: Optional[str]


    def get_kb_id(self):
        if self._ke_client is None:
            raise ValueError("KI's weren't added to any client, use: `<KEClient>.add(<KEClientInteraction>)` ")
        return self._kb_id

    def __init__(self):
        self._ke_client = None
        self._client_ki = {}

    def get_ki(self, name: str):
        return self._client_ki[name]

    def list_ki(self):
        return self._client_ki.values()

    def _set_ki_(self, gp_name: str, handler, ki_type: str) -> KnowledgeInteraction:
        from ke_client.client._ki_utils import require_graph_pattern
        gp = require_graph_pattern(gp_name)
        ki = KnowledgeInteraction(ki_name=f"{ki_type}-{gp.name}", handler=handler, ki_type=ki_type, graph_pattern=gp)
        if ki.ki_name in self._client_ki:
            raise Exception(f"Duplicate knowledge interaction '{gp.name}' ({ki.ki_type}).")
        self._client_ki[ki.ki_name] = ki
        return ki

    @staticmethod
    def _deco_ctx():
        caller_ctx = inspect.getframeinfo(inspect.stack()[2][0])
        ctx = f"{"\n".join([s.strip() for s in caller_ctx.code_context])}"
        return ctx

    @property
    def _client(self) -> KERequestClient:
        if self._ke_client is None:
            raise ValueError("KI's weren't added to any client, use: `<KEClient>.add(<KEClientInteraction>)` ")
        return self._ke_client

    def _set_client(self, kb_id: str, ke_client: KERequestClient):
        if self._ke_client is not None:
            raise ValueError("KI's have been already added to client ")
        self._ke_client = ke_client
        self._kb_id = kb_id

    # region deco
    def post(self, name: str) -> \
            Callable[
                [
                    [Callable[..., KIBindings]],
                ], Callable[..., KIPostResponse]]:
        # ki : GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.POST)
        call_ctx = self._deco_ctx()

        def deco(func: Callable[..., KIBindings]) -> Callable[..., KIPostResponse]:
            ki: KnowledgeInteraction = self._set_ki_(gp_name=name, handler=func,
                                                     ki_type=KnowledgeInteractionType.POST)
            func_sig = inspect.signature(func)
            verify_out_bindings_ki(gp_name=name, bindings_annotation=func_sig.return_annotation,
                                   call_ctx=call_ctx)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIPostResponse:
                ki_id = self._client_ki[ki.ki_name].ki_id
                if ki_id is None:
                    raise KIError(
                        message=f"Empty 'ki_id' for graph pattern: {ki.ki_name}. Is graph pattern registered? ",
                        ctx=call_ctx)
                logging.info(f"POST init bindings: {ki_id}")
                post_bindings = func(*wrapper_args, **kwargs)

                ke_request_json = prepare_ke_request(bindings=post_bindings, ki=ki, call_ctx=call_ctx)
                ki_post_response: KIPostResponse = self._client.post_ke(bindings=ke_request_json, ki_id=ki_id,
                                                                        ki_name=ki.ki_name)
                return ki_post_response

            return wrapper

        return deco

    def ask(self, name: str) -> \
            Callable[
                [
                    [Callable[..., KIBindings]],
                ], Callable[..., KIAskResponse]]:
        call_ctx = self._deco_ctx()

        def deco(func: Callable[..., KIBindings]) -> Callable[..., KIAskResponse]:
            func_sig = inspect.signature(func)
            verify_out_bindings_ki(gp_name=name, bindings_annotation=func_sig.return_annotation,
                                   call_ctx=call_ctx)
            ki: KnowledgeInteraction = self._set_ki_(gp_name=name, handler=func,
                                                     ki_type=KnowledgeInteractionType.ASK)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIAskResponse:
                ki_id = self._client_ki[ki.ki_name].ki_id
                if ki_id is None:
                    raise KIError(
                        message=f"Empty 'ki_id' for graph pattern: {ki.ki_name}. Is graph pattern registered? ",
                        ctx=call_ctx)

                logging.info(f"ASK init bindings: {ki_id}")
                ask_bindings = func(*wrapper_args, **kwargs)
                ke_request_json = prepare_ke_request(bindings=ask_bindings, ki=ki, call_ctx=call_ctx)

                result_bindings: KIAskResponse = self._client.ask_ke(bindings=ke_request_json, ki_id=ki_id,
                                                                     ki_name=ki.ki_name)

                logging.debug(f"ASK-{ki_id}-result: {result_bindings}")
                return result_bindings

            return wrapper

        return deco

    def react(self, name: str) -> Callable[[Callable[[str, Optional[KIBindings]], KIBindings]], \
            Callable[[str, Optional[KIBindings]], KIBindings]]:
        call_ctx = self._deco_ctx()

        def deco(func: Callable[[str, Optional[KIBindings]], KIBindings]) -> \
                Callable[[str, Optional[KIBindings]], KIBindings]:
            func_sig = inspect.signature(func)
            params = {k: param for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            # verify schema
            verify_in_bindings_ki(gp_name=name, params=params, call_ctx=call_ctx)
            verify_out_bindings_ki(gp_name=name, bindings_annotation=func_sig.return_annotation,
                                   call_ctx=call_ctx)

            ki: KnowledgeInteraction

            # def wrapper(*wrapper_args,**kwargs ) -> KIBindings:
            @wraps(func)
            def wrapper(*wrapper_args) -> KIBindings:
                _kwargs = _init_ki_kwargs(wrapper_args=wrapper_args, params=params)
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                post_input_bindings = _kwargs["bindings"] if "bindings" in _kwargs else None
                logging.info(f"REACT init bindings: {ki_id}")
                # logging.debug(f"REACT init bindings: {ki_id} :{post_input_bindings}")
                react_bindings: Union[List[Dict], List[BindingsBase]] = func(**_kwargs)
                if react_bindings is None:
                    logging.warning(f"Undefined react_bindings for {ki_id}, setting empty list")
                    react_bindings = []
                _verify_mismatched_bindings(ki_id, post_input_bindings, react_bindings)
                ke_request_json = prepare_ke_request(bindings=react_bindings, ki=ki, call_ctx=call_ctx)
                return ke_request_json

            wrapper.__name__ = wrapper.__name__ + "_" + func.__name__
            ki: KnowledgeInteraction = self._set_ki_(gp_name=name, handler=wrapper,
                                                     ki_type=KnowledgeInteractionType.REACT)
            # self._set_ki_(gp=gp, handler=wrapper, ki_type=KnowledgeInteractionType.REACT)
            return wrapper

        return deco

    def answer(self, name: str):
        # gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.ANSWER)
        call_ctx = self._deco_ctx()

        def deco(func: Callable[[str, Optional[KIBindings]], KIBindings]):
            func_sig = inspect.signature(func)
            params = {k: param for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            verify_in_bindings_ki(gp_name=name, params=params, call_ctx=call_ctx)
            verify_out_bindings_ki(gp_name=name, bindings_annotation=func_sig.return_annotation, call_ctx=call_ctx)
            ki: KnowledgeInteraction

            def wrapper(*wrapper_args):
                _kwargs = _init_ki_kwargs(wrapper_args=wrapper_args, params=params)
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                input_bindings: list[dict] = _kwargs["bindings"] if "bindings" in _kwargs else None

                logging.info(f"ANSWER init bindings: {ki_id}")
                logging.debug(f"ANSWER init bindings: {ki_id} :{input_bindings}")
                _verify_required_bindings(gp=ki.graph_pattern, ki_bindings=input_bindings, call_ctx=call_ctx)

                answer_bindings = func(**_kwargs)
                _verify_mismatched_bindings(ki_id, input_bindings, answer_bindings)
                ke_request_json = prepare_ke_request(bindings=answer_bindings, ki=ki, call_ctx=call_ctx)
                return ke_request_json

            wrapper.__name__ = wrapper.__name__ + "_" + func.__name__
            ki: KnowledgeInteraction = self._set_ki_(gp_name=name, handler=wrapper,
                                                     ki_type=KnowledgeInteractionType.ANSWER)

            return wrapper

        return deco
    # endregion
