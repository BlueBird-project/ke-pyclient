import inspect
import logging.config
import threading
import time
from functools import wraps
from logging import Logger
from typing import Union, Callable, ParamSpec, Optional, List, Dict, Any, get_args, get_origin, \
    Iterable, Tuple, TypeAlias

import ke_client.ke_vars as ke_vars
from ke_client.client._ki_bindings import BindingsBase
from ke_client.client._ki_exceptions import KIError, KITypeError

from ke_client.client._client_base import KEClientBase
from ke_client.client._ke_properties import KnowledgeInteractionTypeName
from ke_client.client._ki_utils import init_ki_graph_pattern, verify_input_bindings, verify_output_bindings, \
    _serialize_returned_bindings, verify_binding_args, _verify_required_bindings
from ke_client.ki_model import KnowledgeInteractionType, KIPostResponse, KIAskResponse, GraphPattern
from ke_client.utils import validate_kb_id

P = ParamSpec("P")
KIBindings: TypeAlias = List[Union[Dict[str, Any], BindingsBase]]


# TODO: move threading features to other module


def verify_mismatched_bindings(ki_id: str, input_bindings, output_bindings):
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


class KEClient(KEClientBase):
    # region fields
    kb_id: str
    kb_name: str
    ke_rest_endpoint: str
    kb_description: Optional[str] = None
    # TODO: validate reasoner_level can be equal only to 1,2,3,4
    reasoner_level: int = 1
    prefixes: dict

    # client loop
    _handler_loop_thread_: Optional[threading.Thread] = None
    # stop event for the client loop
    _stop_event_: Optional[threading.Event] = None

    # endregion

    @classmethod
    def build(cls, kb_id: Optional[str] = None, logger: Optional[Logger] = None) -> 'KEClient':
        from ke_client import ke_settings, ki_conf as ki
        if ki is None:
            from ke_client import configure_ki
            logging.info("Configuring KI settings")
            ki = configure_ki()
        if kb_id is None:
            kb_id = ke_settings.knowledge_base_id
        if kb_id is None:
            raise Exception(
                "Undefined knowledge_base_id: 'kb_id' of build()   and  'ke_knowledge_base_id'  variables are None")

        return cls(kb_id=kb_id, ke_rest_endpoint=ke_settings.rest_endpoint, kb_name=ki.kb_name,
                   kb_description=ki.kb_description, logger=logger, prefixes=ki.prefixes)

    def __init__(self, kb_id: str, kb_name: str, ke_rest_endpoint: str, kb_description: str,
                 verify_cert: bool = ke_vars.VERIFY_SERVER_CERT, logger: Optional[Logger] = None,
                 prefixes: Optional[dict] = None):
        """

        :param kb_id: knowledge base URI
        :param kb_name:
        :param ke_rest_endpoint:
        :param kb_description:
        :param verify_cert:
        :param logger:
        :param prefixes:
        """
        kb_id = validate_kb_id(kb_id)
        if not ke_rest_endpoint.endswith("/"):
            ke_rest_endpoint = ke_rest_endpoint + "/"
        if not ke_rest_endpoint.endswith("/rest/"):
            raise ValueError("Invalid rest endpoint, valid template:"
                             + " with basic auth: {protocol}://{user}:{password}@{host}:{port}/rest/ "
                             + " without basic auth: {protocol}://{host}:{port}/rest/ "
                             )

        if prefixes is None:
            prefixes = {}
        super().__init__(kb_id=kb_id, kb_name=kb_name, ke_rest_endpoint=ke_rest_endpoint, kb_description=kb_description,
                         prefixes=prefixes)
        self._verify_cert_ = verify_cert
        self._logger_ = logging.getLogger() if logger is None else logger
        self._logger_.info(f"Initialized client to {ke_rest_endpoint}")

    # region interaction

    def _ask_(self, bindings: list[dict[str, str]], ki_id: str, ) -> KIAskResponse:
        """
        ASK for knowledge with query bindings to receive bindings for an ASK knowledge interaction.
        """
        ki_name = self._registered_ki_[ki_id].name
        logging.info(f"ASK REQUEST={ki_id}:{ki_name}")
        # self._assert_client_state_()
        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/ask",
                                           headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                                           json=bindings, )

        self._assert_response_(response, gp_name=ki_name)
        ask_response = KIAskResponse.model_validate(response.json())

        # return response.json()["bindingSet"]
        return ask_response

    def _post_(self, bindings: list[dict[str, str]], ki_id: str, ) -> \
            KIPostResponse:
        """
        POST knowledge interactions - post bindings for defined graph pattern
        """
        gp = self._registered_ki_[ki_id].graph_pattern
        ki_name = gp.name
        logging.info(f"POST REQUEST={ki_id}:{ki_name}")
        # self._assert_client_state_()
        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/post",
                                           headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                                           json=bindings, )

        self._assert_response_(response, gp_name=ki_name)
        post_response = KIPostResponse.model_validate(response.json())

        # result_binding_set = response.json()["resultBindingSet"]
        # result_binding_set = post_response.resultBindingSet
        # if len(result_binding_set) == 0 and gp.result_pattern_value is not None:
        #     exchange_info = response.json()["exchangeInfo"]
        #     accu = []
        #     arg_accu = []
        #     for ei in exchange_info:
        #         result_binding_set = ei["resultBindingSet"]
        #         filtered_bindings_set = [gp.get_result_pattern_bindings(result_binding_set=binding_set)
        #                                  for binding_set in result_binding_set]
        #         arg_accu += [x['argumentBindingSet'] for x in response.json()["exchangeInfo"]]
        #         accu += filtered_bindings_set
        #     return post_response
        return post_response

    # endregion

    # region deco
    # experimental client merge
    def include(self, ki_client: 'KEClientBase'):
        for ki in ki_client.list_ki():
            self._set_ki_(gp=ki.graph_pattern, handler=ki.handler, ki_type=ki.ki_type)

    @staticmethod
    def _deco_ctx():
        caller_ctx = inspect.getframeinfo(inspect.stack()[2][0])
        ctx = f"{"\n".join([s.strip() for s in caller_ctx.code_context])}"
        return ctx

    def post(self, name: str) -> \
            Callable[
                [
                    [Callable[[...], KIBindings]],
                ], Callable[[...], KIPostResponse]]:
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.POST)
        call_ctx = self._deco_ctx()

        def deco(func: Callable[[...], KIBindings]) -> Callable[[...], KIPostResponse]:
            self._set_ki_(gp=gp, handler=func, ki_type=KnowledgeInteractionType.POST)
            func_sig = inspect.signature(func)
            # params = {k: param for k, param in func_sig.parameters.items() if
            #           param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            # verify schema
            # verify_input_bindings(name=name, params=params, call_ctx=call_ctx)
            wrapped_response = verify_output_bindings(name=name, bindings_annotation=func_sig.return_annotation,
                                                      call_ctx=call_ctx)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIPostResponse:
                ki_id = self._client_ki_[gp.name].ki_id
                if ki_id is None:
                    raise KIError(message=f"Empty 'ki_id' for graph pattern: {gp.name}. Is graph pattern registered? ",
                                  ctx=call_ctx)
                logging.info(f"POST init bindings: {ki_id}")
                post_bindings = func(*wrapper_args, **kwargs)
                ki_bindings = _serialize_returned_bindings(ki_id=ki_id, is_response_wrapped=wrapped_response,
                                                           bindings=post_bindings,
                                                           ki_type=KnowledgeInteractionType.POST)
                verify_binding_args(name=name, ki_type=KnowledgeInteractionType.POST, ki_bindings=ki_bindings,
                                    call_ctx=call_ctx)
                ki_post_response: KIPostResponse = self._post_(bindings=post_bindings, ki_id=ki_id)
                return ki_post_response

            return wrapper

        return deco

    def ask(self, name: str) -> \
            Callable[
                [
                    [Callable[[...], KIBindings]],
                ], Callable[[...], KIAskResponse]]:
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.ASK)
        call_ctx = self._deco_ctx()

        # verify_binding_args(name, ki_binding_args=args, call_ctx=call_ctx)

        def deco(func: Callable[[...], KIBindings]) -> Callable[[...], KIAskResponse]:
            func_sig = inspect.signature(func)
            # params = {k: param for k, param in func_sig.parameters.items() if
            #           param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            # verify schema
            # verify_input_bindings(name=name, params=params, call_ctx=call_ctx)
            wrapped_response = verify_output_bindings(name=name, bindings_annotation=func_sig.return_annotation,
                                                      call_ctx=call_ctx)
            self._set_ki_(gp=gp, handler=func, ki_type=KnowledgeInteractionType.ASK)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIAskResponse:
                ki_id = self._client_ki_[gp.name].ki_id
                if ki_id is None:
                    raise KIError(message=f"Empty 'ki_id' for graph pattern: {gp.name}. Is graph pattern registered? ",
                                  ctx=call_ctx)

                logging.info(f"ASK init bindings: {ki_id}")
                ask_bindings = func(*wrapper_args, **kwargs)
                ki_bindings = _serialize_returned_bindings(ki_id=ki_id, is_response_wrapped=wrapped_response,
                                                           bindings=ask_bindings,
                                                           ki_type=KnowledgeInteractionType.ASK)
                verify_binding_args(name=name, ki_type=KnowledgeInteractionType.ASK, ki_bindings=ki_bindings,
                                    call_ctx=call_ctx)
                # if query_bindings is None:
                #     query_bindings = [{}]
                # logging.debug(f"ASK bindings: {ki_id} = {query_bindings}")
                # if type(query_bindings) is not list:
                #     query_bindings = [query_bindings]
                # _check_missing_bindings(name=name, ki_bindings=ki_bindings, call_ctx=call_ctx)
                # syntax_bindings_verification(name=name, ki_bindings=query_bindings, call_ctx=call_ctx)
                result_bindings: KIAskResponse = self._ask_(bindings=ki_bindings, ki_id=ki_id)

                logging.debug(f"ASK-{ki_id}-result: {result_bindings}")
                return result_bindings

            return wrapper

        return deco

    # def react(self, name: str, args: Optional[List[str]] = None, response_class: Optional[Type[BindingsBase]] = None):
    def react(self, name: str) -> Callable[[Callable[[str, Optional[KIBindings]], KIBindings]], \
            Callable[[str, Optional[KIBindings]], KIBindings]]:
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.REACT)
        call_ctx = self._deco_ctx()

        def deco(func: Callable[[str, Optional[KIBindings]], KIBindings]) -> \
                Callable[[str, Optional[KIBindings]], KIBindings]:
            func_sig = inspect.signature(func)
            params = {k: param for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            # verify schema
            verify_input_bindings(name=name, params=params, call_ctx=call_ctx)
            wrapped_response = verify_output_bindings(name=name, bindings_annotation=func_sig.return_annotation,
                                                      call_ctx=call_ctx)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIBindings:
                # _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
                #            k in params}
                _kwargs = _init_ki_kwargs(wrapper_args=wrapper_args, params=params)
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                post_input_bindings = _kwargs["bindings"] if "bindings" in _kwargs else None
                # logging.info(f"REACT({name}): {ki_id}")
                logging.info(f"REACT init bindings: {ki_id}")
                # logging.debug(f"REACT init bindings: {ki_id} :{post_input_bindings}")
                react_bindings: Union[List[Dict], List[BindingsBase]] = func(**_kwargs)

                verify_mismatched_bindings(ki_id, post_input_bindings, react_bindings)
                ki_bindings = _serialize_returned_bindings(ki_id=ki_id, is_response_wrapped=wrapped_response,
                                                           bindings=react_bindings,
                                                           ki_type=KnowledgeInteractionType.REACT)
                verify_binding_args(name=name, ki_type=KnowledgeInteractionType.REACT, ki_bindings=ki_bindings,
                                    call_ctx=call_ctx)
                return ki_bindings

            wrapper.__name__ = wrapper.__name__ + "_" + func.__name__
            self._set_ki_(gp=gp, handler=wrapper, ki_type=KnowledgeInteractionType.REACT)
            return wrapper

        return deco

    def answer(self, name: str):
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionTypeName.ANSWER)
        call_ctx = self._deco_ctx()

        def deco(func: Callable[[str, Optional[KIBindings]], KIBindings]):
            func_sig = inspect.signature(func)
            params = {k: param for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD}
            verify_input_bindings(name=name, params=params, call_ctx=call_ctx)
            wrapped_response = verify_output_bindings(name=name, bindings_annotation=func_sig.return_annotation,
                                                      call_ctx=call_ctx)

            def wrapper(*wrapper_args, **kwargs):
                _kwargs = _init_ki_kwargs(wrapper_args=wrapper_args, params=params)
                # _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
                #            k in params}
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                input_bindings: list[dict] = _kwargs["bindings"] if "bindings" in _kwargs else None

                logging.info(f"ANSWER init bindings: {ki_id}")
                logging.debug(f"ANSWER init bindings: {ki_id} :{input_bindings}")
                _verify_required_bindings(gp=gp, ki_bindings=input_bindings, call_ctx=call_ctx)

                answer_bindings = func(**_kwargs)
                verify_mismatched_bindings(ki_id, input_bindings, answer_bindings)
                ki_bindings = _serialize_returned_bindings(ki_id=ki_id, is_response_wrapped=wrapped_response,
                                                           bindings=answer_bindings,
                                                           ki_type=KnowledgeInteractionType.ANSWER)
                verify_binding_args(name=name, ki_type=KnowledgeInteractionType.ANSWER, ki_bindings=ki_bindings,
                                    call_ctx=call_ctx)
                return ki_bindings
                # if answer_bindings is None:
                #     answer_bindings = []
                # if type(answer_bindings) is not list:
                #     answer_bindings = [answer_bindings]
                # if len(input_bindings) > 0 and len(answer_bindings) > 0:
                #     ikeys = [ik for ik in input_bindings[0].keys() if ik in answer_bindings[0].keys()]
                #     # provided values for the input bindings in the ASK KI should be the same in the ANSWER KI
                #     for ik in ikeys:
                #         inp_values = {str(ib[ik]) for ib in input_bindings}
                #         err_values = {str(ab[ik]) for ab in answer_bindings if str(ab[ik]) not in inp_values}
                #         if len(err_values) > 0:
                #             raise Exception(
                #                 f"input bindings don't match output bindings for key: {ik}, values: {err_values}")
                # # verify_bindings(name=name, ki_bindings=answer_bindings)
                # return answer_bindings

            wrapper.__name__ = wrapper.__name__ + "_" + func.__name__
            self._set_ki_(gp=gp, handler=wrapper, ki_type=KnowledgeInteractionType.ANSWER)

            return wrapper

        return deco

    # endregion

    # region client's main loop
    def _handler_loop_tick_(self):
        response = self._api_get_request_(self.ke_rest_endpoint + "sc/handle",
                                          headers={"Knowledge-Base-Id": self.kb_id})
        if response.status_code == 200:
            # 200 means: we receive bindings that we need to handle, then re-poll asap.
            self._handle_response_(response=response)
            return True
        elif response.status_code == 202:
            # 202 means: re poll (heartbeat)
            # continue
            return True
        elif response.status_code == 410:
            # 410 means: KE has stopped, so terminate  # TODO catch error /self.logger
            # break
            self.logger.warning(f"Received{response.status_code}")
            time.sleep(30)
            return False
        else:
            self.logger.warning(f"received unexpected status {response.status_code}")
            self.logger.warning(response.text)
            self.logger.info("Re-polling after a short timeout")
            time.sleep(15)
            return True
            # continue

    def _handler_loop_worker_(self, stop_event: threading.Event):
        self.logger.info("Start handler loop")

        while not stop_event.is_set():

            if not self._handler_loop_tick_():
                break

    def _handler_loop_(self, ):
        self.logger.info("Start handler loop")
        self._is_running_ = True
        while True:
            if not self._handler_loop_tick_():
                break

    # endregion

    # region client control

    def start(self):
        self._stop_event_ = threading.Event()

        # Create and start thread
        self._handler_loop_thread_ = threading.Thread(target=self._handler_loop_worker_, args=(self._stop_event_,))
        self._handler_loop_thread_.start()

    def start_sync(self):
        if self._handler_loop_thread_ is not None or self._stop_event_ is not None:
            raise RuntimeError("Client has already started  in background")
        try:
            self._handler_loop_()
        finally:
            self._is_running_ = False

    def stop(self):
        if self._stop_event_ is not None:
            self._stop_event_.set()
            self._handler_loop_thread_.join()
            self._stop_event_ = None
            self._handler_loop_thread_ = None

    def state(self) -> bool:
        if self._handler_loop_thread_ is not None:
            return self._handler_loop_thread_.is_alive() and not self._stop_event_.is_set()
        return self._is_running_
    # endregion
