import inspect
import logging.config
import threading
import time
from functools import wraps
from logging import Logger
from typing import Union, Callable, ParamSpec, Optional, List, Dict, Any, Type

import ke_client.ke_vars as ke_vars
from ke_client.client._ki_bindings import BindingsBase
from ke_client.client._ki_exceptions import KIError

from ke_client.client._client_base import KEClientBase
from ke_client.client._ke_properties import KnowledgeInteractionNames
from ke_client.client._ki_utils import init_ki_graph_pattern, verify_binding_args, syntax_bindings_verification, \
    verify_required_bindings
from ke_client.ki_model import KnowledgeInteractionType, KIPostResponse, KIAskResponse, GraphPattern
from ke_client.utils import validate_kb_id

P = ParamSpec("P")


# TODO: move threading features to other module

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
            raise Exception("Undefined knowledge_base_id. 'kb_id' and  'ke_knowledge_base_id' variable are None")

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
            self._set_ki_(gp=ki.graph_pattern, handler=ki.handler, ki_type=ki.type)

    @staticmethod
    def _deco_ctx():
        caller_ctx = inspect.getframeinfo(inspect.stack()[2][0])
        ctx = f"{"\n".join([s.strip() for s in caller_ctx.code_context])}"
        return ctx

    def post(self, name: str, args: Optional[List[str]] = None, response_class: Optional[Type[BindingsBase]] = None) -> \
            Callable[
                [Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]],
                Callable[[List[Dict[str, Any]]], KIPostResponse]
            ]:
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionNames.POST)
        call_ctx = self._deco_ctx()
        verify_binding_args(name, ki_binding_args=args, call_ctx=call_ctx, response_class=response_class)

        def deco(func: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]) -> \
                Callable[[List[Dict[str, Any]]], KIPostResponse]:
            self._set_ki_(gp=gp, handler=func, ki_type=KnowledgeInteractionType.POST)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIPostResponse:
                ki_id = self._client_ki_[gp.name].ki_id
                if ki_id is None:
                    raise KIError(message=f"Empty 'ki_id' for graph pattern: {gp.name}. Is graph pattern registerd? ",
                                  ctx=call_ctx)
                logging.info(f"POST init bindings: {ki_id}")
                post_bindings = func(*wrapper_args, **kwargs)
                logging.debug(f"POST bindings: {ki_id} = {post_bindings}")
                if post_bindings is None:
                    post_bindings = [{}]
                if type(post_bindings) is not list:
                    post_bindings = [post_bindings]
                syntax_bindings_verification(name=name, ki_bindings=post_bindings, call_ctx=call_ctx)
                # result_bindings,argument_binding = self._post_(bindings=post_bindings, ki_id=ki_id)
                ki_post_response: KIPostResponse = self._post_(bindings=post_bindings, ki_id=ki_id)
                return ki_post_response

            return wrapper

        return deco

    def ask(self, name: str, args: Optional[List[str]] = None) -> \
            Callable[
                [Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]],
                Callable[[List[Dict[str, Any]]], KIAskResponse]
            ]:

        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionNames.ASK)
        call_ctx = self._deco_ctx()
        verify_binding_args(name, ki_binding_args=args, call_ctx=call_ctx)

        def deco(func: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]) -> \
                Callable[[List[Dict[str, Any]]], KIAskResponse]:
            self._set_ki_(gp=gp, handler=func, ki_type=KnowledgeInteractionType.ASK)

            @wraps(func)
            def wrapper(*wrapper_args, **kwargs) -> KIAskResponse:
                ki_id = self._client_ki_[gp.name].ki_id
                if ki_id is None:
                    raise KIError(message=f"Empty 'ki_id' for graph pattern: {gp.name}. Is graph pattern registerd? ",
                                  ctx=call_ctx)

                logging.info(f"ASK init bindings: {ki_id}")
                query_bindings = func(*wrapper_args, **kwargs)
                if query_bindings is None:
                    query_bindings = [{}]
                logging.debug(f"ASK bindings: {ki_id} = {query_bindings}")
                if type(query_bindings) is not list:
                    query_bindings = [query_bindings]
                verify_required_bindings(name=name, ki_bindings=query_bindings, call_ctx=call_ctx)
                syntax_bindings_verification(name=name, ki_bindings=query_bindings, call_ctx=call_ctx)
                result_bindings: KIAskResponse = self._ask_(bindings=query_bindings, ki_id=ki_id)

                logging.debug(f"ASK-{ki_id}-result: {result_bindings}")
                return result_bindings

            return wrapper

        return deco

    def react(self, name: str, args: Optional[List[str]] = None, response_class: Optional[Type[BindingsBase]] = None):
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionNames.REACT)
        call_ctx = self._deco_ctx()
        verify_binding_args(name, ki_binding_args=args, call_ctx=call_ctx, response_class=response_class)

        def deco(func: Callable[[str, Optional[Dict[str, Any]]], Union[List[Dict[str, Any]], Dict[str, Any]]]):
            func_sig = inspect.signature(func)
            params = [k for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD]

            def wrapper(*wrapper_args, **kwargs):
                _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
                           k in params}
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                post_input_bindings = _kwargs["bindings"] if "bindings" in _kwargs else None
                # logging.info(f"REACT({name}): {ki_id}")
                logging.info(f"REACT init bindings: {ki_id}")
                logging.debug(f"REACT init bindings: {ki_id} :{post_input_bindings}")
                react_bindings = func(**_kwargs)
                if react_bindings is None:
                    react_bindings = []
                logging.debug(f"REACT bindings: {ki_id} = {react_bindings}")

                if type(react_bindings) is not list:
                    react_bindings = [react_bindings]
                # verify_bindings(name=name, ki_bindings=react_bindings)
                return react_bindings

            wrapper.__name__ = wrapper.__name__ + "_" + func.__name__
            self._set_ki_(gp=gp, handler=wrapper, ki_type=KnowledgeInteractionType.REACT)
            return wrapper

        return deco

    def answer(self, name: str, args: Optional[List[str]] = None):
        gp: GraphPattern = init_ki_graph_pattern(name, KnowledgeInteractionNames.ANSWER)
        call_ctx = self._deco_ctx()
        verify_binding_args(name, ki_binding_args=args, call_ctx=call_ctx)

        def deco(func: Callable[[str, Optional[Dict[str, Any]]], Union[List[Dict[str, Any]], Dict[str, Any]]]):
            func_sig = inspect.signature(func)
            params = [k for k, param in func_sig.parameters.items() if
                      param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD]

            # for k, param in func_sig.parameters.items():
            #     print(k,param)

            def wrapper(*wrapper_args, **kwargs):
                _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
                           k in params}
                ki_id = _kwargs["ki_id"] if "ki_id" in _kwargs else None
                input_bindings: list[dict] = _kwargs["bindings"] if "bindings" in _kwargs else None

                logging.info(f"ANSWER init bindings: {ki_id}")
                logging.debug(f"ANSWER init bindings: {ki_id} :{input_bindings}")
                verify_required_bindings(name=name, ki_bindings=input_bindings, call_ctx=call_ctx)
                answer_bindings = func(**_kwargs)
                if answer_bindings is None:
                    answer_bindings = []
                logging.debug(f"ANSWER bindings:{ki_id} = {answer_bindings}")
                if type(answer_bindings) is not list:
                    answer_bindings = [answer_bindings]
                if len(input_bindings) > 0 and len(answer_bindings) > 0:
                    ikeys = [ik for ik in input_bindings[0].keys() if ik in answer_bindings[0].keys()]
                    # provided values for the input bindings in the ASK KI should be the same in the ANSWER KI
                    for ik in ikeys:
                        inp_values = {str(ib[ik]) for ib in input_bindings}
                        err_values = {str(ab[ik]) for ab in answer_bindings if str(ab[ik]) not in inp_values}
                        if len(err_values) > 0:
                            raise Exception(
                                f"input bindings don't match output bindings for key: {ik}, values: {err_values}")
                # verify_bindings(name=name, ki_bindings=answer_bindings)
                return answer_bindings

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
