import logging
from logging import Logger
from typing import Union, Callable, Dict, Optional, Any, List
from http import HTTPStatus
import requests
import time

from pydantic import BaseModel

from ke_client.ke_pyclient._ki_utils import default_handler

from requests import Response

import _ke_rest_response_errors as response_errors
from ke_client.ki_model import GraphPattern
from ke_client.ki_model import KnowledgeInteractionType, KnowledgeInteraction, ExchangeInfoStatus
import ke_client.ke_vars as ke_vars


class KEClientBase(BaseModel):
    # region private fields
    _logger_: Logger = None
    # dictionary of the knowledge interactions used in the local service (
    _client_ki_: Dict[str, KnowledgeInteraction] = {}
    _is_registered_ = False
    _is_ki_registered_ = False
    # dictionary of the knowledge interactions registered in the KE server
    _registered_ki_: Optional[Dict[str, KnowledgeInteraction]] = None
    # verify KE certificate if SSL is on
    _verify_cert_: bool = True
    # state of client
    _is_running_: bool = False
    _is_reconnecting_: bool = False
    _current_wait_timeout_: int = 30

    # endregion

    def __init__(self,
                 verify_cert: bool = ke_vars.VERIFY_SERVER_CERT, logger: Optional[Logger] = None, **kwargs):
        self._verify_cert_ = verify_cert
        self._logger_ = logging.getLogger() if logger is None else logger
        super().__init__(**kwargs)

    # region ki meta

    @property
    def logger(self):
        return self._logger_

    @property
    def is_registered(self):
        return self._is_registered_ and self._is_ki_registered_

    def get_ki(self, name: str):
        return self._client_ki_[name]

    def list_ki(self):
        return self._client_ki_.values()

    def get_registered_ki(self, ki_id: str):
        return self._registered_ki_[ki_id]

    def list_registered_ki(self):
        return self._registered_ki_.values()

    # endregion

    # region interaction utils
    def _assert_response_(self, response: requests.Response, gp_name: Optional[str] = None):
        """
        check if the response from the knowledge engine is correct
        :param response: response from KE
        :param gp_name: name of the method sending request to the KE
        :return:
        """
        gp_name = gp_name if gp_name is not None else "<none_gp_name>"
        if not response.ok:
            err = f"Invalid response for {gp_name}: {response.status_code}"
            # resp_content = None
            try:
                resp_content = response.json()
            except Exception as err:
                self.logger.warning(f"{err}:  Error content is not JSON: {response.text}")
                raise Exception("Invalid response")
            # if resp_content is not None:
            if response.status_code == 404 and response.json()["message"] in [response_errors.INACTIVITY_404_ERROR,
                                                                              response_errors.REGISTER_404_ERROR]:
                self.logger.error(f"{err}: {response.json()["message"]}")
                # self.register()
                self.reconnect()
            else:
                self.logger.error(f"Unknown {err}: {resp_content} ")

        assert response.ok
        try:
            resp_content = response.json()
        except Exception as err:
            if response.text == "":
                self.logger.warning(
                    f"Empty response for {gp_name} with status 'OK' (HTTP 200)." +
                    "Url: 'http://localhost:8280/rest/sc/handle'." +
                    "It's likely to be KE server issue. ")
            else:
                self.logger.warning(f"{err}:  content is not JSON: {response.text}")
            resp_content = {}
        if "exchangeInfo" in resp_content:
            exchange_info_list = resp_content["exchangeInfo"]
            if type(exchange_info_list) is not list:
                raise Exception(
                    f"Failed KI ({gp_name}) expected 'exchangeInfo' type is 'list' not '{type(exchange_info_list)}' ")

            for exchange_info in exchange_info_list:
                if exchange_info["status"].lower() == ExchangeInfoStatus.FAILED.lower():
                    bindings = exchange_info["bindings"] if "bindings" in exchange_info else None
                    raise Exception(
                        f"Failed KI({gp_name},status: {exchange_info["status"]}): " +
                        f"{exchange_info["failedMessage"]}, bindings:{bindings}")

    # endregion

    # region registration/init

    def register(self):
        if not self._is_registered_:
            self._is_ki_registered_ = False
            self._register_knowledge_base_()
            self._check_registered_ki_()
            self._is_ki_registered_ = True

    def reconnect(self, timeout_s: int = 30):
        if self._is_reconnecting_:
            time.sleep(self._is_reconnecting_)
            return
            # TODO: try reconnecting until its possible
        self._is_reconnecting_ = True
        self._current_wait_timeout_ = max(timeout_s, 5)
        max_attempts = 5  # TODO: configurable
        i = 0
        is_connected = False
        while i < max_attempts and not is_connected:
            self.logger.info(f"Reconnecting in {self._current_wait_timeout_}, attempt:{i}")
            time.sleep(self._current_wait_timeout_)
            i += 1
            try:
                self._reconnect_procedure_()
            except Exception as err:
                self.logger.error(f"Failed to reconnect {err}")
            self._current_wait_timeout_ = min(int(self._current_wait_timeout_ * 1.5), 600)
            is_connected = self.state()

        self._is_reconnecting_ = False

    # region registration private
    def _set_ki_(self, gp: GraphPattern, handler, ki_type: str):
        ki = KnowledgeInteraction(name=gp.name, handler=handler, type=ki_type, graph_pattern=gp)
        if gp.name in self._client_ki_:
            raise Exception(f"Duplicate knowledge interaction '{gp.name}' ({ki.type}).")
        self._client_ki_[gp.name] = ki

    def _assert_client_state_(self):
        if not self._is_registered_:
            raise RuntimeError("Client is not registered")
        if not self.state():
            raise RuntimeError("Client is not running")

    def _register_knowledge_interaction_(self, ki: KnowledgeInteraction) -> str:
        if not self._is_registered_:
            raise RuntimeError("Client is not registered")
        gp = ki.graph_pattern

        if ki.type in [KnowledgeInteractionType.ASK, KnowledgeInteractionType.ANSWER]:
            graph_pattern_key = "graphPattern"
        else:
            graph_pattern_key = "argumentGraphPattern"
        prefixes = {**self.prefixes, **gp.prefixes_safe}
        body = {
            "knowledgeInteractionName": ki.name,
            "knowledgeInteractionType": ki.type,
            graph_pattern_key: gp.pattern_value,
            "prefixes": prefixes,
        }
        if gp.result_pattern is not None:
            body["resultGraphPattern"] = gp.result_pattern_value
        response = requests.post(
            self.ke_rest_endpoint + "sc/ki/",
            json=body,
            headers={"Knowledge-Base-Id": self.kb_id},
            verify=self._verify_cert_
        )
        if response.status_code != 200:
            try:
                error_message = (f"Registration failed,status_code: {response.status_code}, "
                                 f"message: {response.json()["message"]}")
            except Exception:
                error_message = f"Registration failed,status_code: {response.status_code}"
            raise Exception(error_message)
        ki_id = response.json()["knowledgeInteractionId"]
        ki.ki_id = ki_id
        self._registered_ki_[ki_id] = ki
        return ki_id

    def _reconnect_procedure_(self):
        # try:
        #     self.stop()
        # except Exception as ex:
        #     self._logger_.error(f"Stop error: {ex}")
        self._registered_ki_ = None
        self._is_registered_ = None
        self.register()

    def _check_registered_ki_(self):
        if self._registered_ki_ is None:
            'knowledgeInteractionName'
            # response = self._get_(endpoint=self.ke_rest_endpoint + "sc/ki/",
            # headers={"Knowledge-Base-Id": self.kb_id},     register=True)
            response = requests.get(
                self.ke_rest_endpoint + "sc/ki/",
                headers={"Knowledge-Base-Id": self.kb_id},
                verify=self._verify_cert_
            )
            if response.status_code == 200:
                for ki in response.json():
                    ki_name = ki["knowledgeInteractionName"]
                    ki_id = ki["knowledgeInteractionId"]
                    # TODO: optional override instead deleting and re registering
                    if ki_name in self._client_ki_:
                        response = requests.delete(
                            self.ke_rest_endpoint + "sc/ki/",
                            headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                            verify=self._verify_cert_
                        )
                        assert response.ok
                    else:
                        # delete interactions which don't exist in current config
                        response = requests.delete(
                            self.ke_rest_endpoint + "sc/ki/",
                            headers={"Knowledge-Base-Id": self.kb_id, "Knowledge-Interaction-Id": ki_id},
                            verify=self._verify_cert_
                        )
                        assert response.ok
                self._registered_ki_ = {}
                for ki in self._client_ki_.values():
                    self._register_knowledge_interaction_(ki)
            else:
                raise Exception(f"Can't check registered interactions, response: {response.status_code}")
                # self.logger.error("Can't check registered interactions")

    def _register_knowledge_base_(self):
        """
        Register a Knowledge Base with the given details at the given endpoint.
        """
        if self._is_registered_:
            self.logger.warning(f"KB {self.kb_id} has been already registered")
            return

        self.logger.info(f"Start register KB: {self.kb_id} - {self.kb_name}")
        # response = self._get_(endpoint=self.ke_rest_endpoint + "sc/ki/", headers={"Knowledge-Base-Id": self.kb_id})
        response = requests.get(
            self.ke_rest_endpoint + "sc/ki/", headers={"Knowledge-Base-Id": self.kb_id},
            verify=self._verify_cert_
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            self.logger.info(f"KB not registered:  {self.kb_id} - {self.kb_name}")

            response = requests.post(
                self.ke_rest_endpoint + "sc/",
                json={
                    "knowledgeBaseId": self.kb_id,
                    "knowledgeBaseName": self.kb_name,
                    "knowledgeBaseDescription": self.kb_description,
                    # "reasonerLevel": 4,
                    "reasonerLevel": self.reasoner_level,
                    # "reasonerEnabled":True
                },
                verify=self._verify_cert_
            )
            # TODO handler error in response
            assert response.ok
            self.logger.info(f"KB registered:  {self.kb_id} - {self.kb_name}")
            self._is_registered_ = True
        elif response.status_code == HTTPStatus.BAD_REQUEST:
            raise Exception(f"KB registration {HTTPStatus.BAD_REQUEST}")
        elif response.status_code == HTTPStatus.OK:
            self.logger.info(f"KB is registered:  {self.kb_id} - {self.kb_name}")
            self._is_registered_ = True
        else:
            pass

    # endregion

    # endregion

    # region handlers and REST API utils

    def _handler_wrapper_(self, ki_id: str,
                          handler: Optional[Callable[[str, Optional[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
                          bindings: Optional[Dict[str, Any]] = None):

        if handler is None:
            handler = default_handler
        self.logger.info(f"Handler arrived: {ki_id}")
        handler(ki_id=ki_id, bindings=bindings)
        # handler(ki_id=ki_id, bindings=bindings)

    def _handle_response_(self, response: requests.Response, ):
        ki_id: Optional[None] = None
        try:
            handle_request = response.json()
            ki_id: str = handle_request["knowledgeInteractionId"]
            # requestingKnowledgeBaseId: str = handle_request["requestingKnowledgeBaseId"]
            handle_request_id = handle_request["handleRequestId"]
            bindings: list[Dict[str, Any]] = handle_request["bindingSet"]
            ki = self._registered_ki_[ki_id]
            result_bindings = ki.handler(ki_id, bindings)
            self._handle_(bindings=result_bindings, ki_id=ki_id, handle_request_id=handle_request_id)
        except Exception as ex:
            self.logger.error(
                f"Error occurred in handle_response kb_id:{self.kb_id} ki_id:{ki_id}, "
                f"status_code: {response.status_code} : {ex}")

    def _api_post_request_(self, endpoint: str, headers: Dict, json: Union[list[dict[str, str]], Dict],
                           register=False) -> Response:
        return self._http_request_wrapper(
            send_request=lambda: requests.post(endpoint, headers=headers, json=json, verify=self._verify_cert_),
            endpoint=endpoint, register=register)

    def _api_get_request_(self, endpoint: str, headers: Dict, register=False) -> Response:
        return self._http_request_wrapper(
            send_request=lambda: requests.get(endpoint, headers=headers, verify=self._verify_cert_),
            endpoint=endpoint, register=register)

    def _http_request_wrapper(self, send_request: Callable[[], Response], endpoint: str, register: bool):
        try:
            if not register:
                self._assert_client_state_()
            return send_request()
        except requests.ConnectionError as err:
            self.logger.error(f"can't connect to {endpoint}: {err}. Next attempt in 30 seconds")
            try:
                #     timeout configure TODO:
                time.sleep(30)
                return send_request()
            except requests.ConnectionError as err:
                self.logger.error(f"can't connect to {endpoint}: {err}")

            # TODO: if self._reconnect_=True
            self.reconnect()
            # what in case of an error ?
            return send_request()

    def _handle_(self, bindings: list[dict[str, str]], ki_id: str, handle_request_id):
        """
        handler request for data , for REACT/ANSWER knowledge interactions
        """
        ki_name = self._registered_ki_[ki_id].name
        logging.info(f"HANDLE REQUEST={ki_id}:{ki_name}")
        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/handle",
                                           headers={"Knowledge-Base-Id": self.kb_id,
                                                    "Knowledge-Interaction-Id": ki_id, },
                                           json={"handleRequestId": handle_request_id, "bindingSet": bindings, }, )

        self._assert_response_(response, gp_name=ki_name)
    # endregion
