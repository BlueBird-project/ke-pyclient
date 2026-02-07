import logging.config
import threading
import time
from logging import Logger
from typing import Union, Optional, List, Dict, Any, TypeAlias

from rdflib import URIRef, Literal

import ke_client.ke_vars as ke_vars
from ke_client.client._ke_request_client import KERequestClient, KERequest
from ke_client.client._ki_bindings import BindingsBase

from ke_client.client._client_base import KEClientBase
from ke_client.client._ki_holder import KIHolder
from ke_client.ki_model import KIPostResponse, KIAskResponse, KnowledgeInteraction
from ke_client.utils import validate_kb_id

KIBindings: TypeAlias = List[Union[Dict[str, Any], BindingsBase]]
OptionalLiteral: TypeAlias = Union[Literal, URIRef, None]
OptionalURIRef: TypeAlias = Union[URIRef, None]


# TODO: move threading features to other module


class KEClient(KEClientBase, KERequestClient, KIHolder):
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

    # region KEHolder
    @property
    def _client(self) -> KERequestClient:
        # override _client property
        return self

    def _add_ki(self, ki: KnowledgeInteraction):
        if ki.ki_name in self._client_ki:
            raise Exception(f"Duplicate knowledge interaction '{ki.graph_pattern.name}' ({ki.ki_type}).")
        self._client_ki[ki.ki_name] = ki

    def include(self, ki_holder: KIHolder):
        ki_holder._set_client(self)
        for ki in ki_holder.list_ki():
            self._set_ki_(gp_name=ki.graph_pattern.name, handler=ki.handler, ki_type=ki.ki_type)

    # endregion
    # region KERequestClient
    def ask_ke(self, bindings: KERequest, ki_id: str, ki_name: str) -> KIAskResponse:
        """
        ASK for knowledge with query bindings to receive bindings for an ASK knowledge interaction.
        """
        # ki_name = self._registered_ki_[ki_id].name
        # logging.info(f"ASK REQUEST={ki_id}:{ki_name}")
        logging.info(f"ASK REQUEST={ki_id} ")
        # self._assert_client_state_()
        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/ask",
                                           headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                                           ke_request=bindings)

        self._assert_response_(response, ki_name=ki_name)
        ask_response = KIAskResponse.model_validate(response.json())

        # return response.json()["bindingSet"]
        return ask_response

    def post_ke(self, bindings: KERequest, ki_id: str, ki_name: str) -> KIPostResponse:
        """
        POST knowledge interactions - post bindings for defined graph pattern
        """
        gp = self._registered_ki_[ki_id].graph_pattern
        ki_name = gp.name
        logging.info(f"POST REQUEST={ki_id}")
        # logging.info(f"POST REQUEST={ki_id}:{ki_name}")
        # self._assert_client_state_()
        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/post",
                                           headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                                           ke_request=bindings)

        self._assert_response_(response, ki_name=ki_name)
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

    # experimental client merge
    # def _include_client(self, ki_client: 'KEClientBase'):
    #     for ki in ki_client.list_ki():
    #         self._set_ki_(gp_name=ki.graph_pattern.name, handler=ki.handler, ki_type=ki.ki_type)

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
