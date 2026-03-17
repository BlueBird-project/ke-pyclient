import logging
from logging import Logger
from threading import Thread, RLock
from typing import Union, Callable, Dict, Optional, Any, List
from http import HTTPStatus
import requests
import time

from ke_client.utils.enum_utils import EnumItem
from pydantic import BaseModel, PrivateAttr

from requests import Response

import ke_client.client._ke_rest_response_errors as response_errors
from ke_client.ki_model import KnowledgeInteractionType, KnowledgeInteraction, ExchangeInfoStatus
import ke_client.ke_vars as ke_vars


class KEClientBase(BaseModel):
    # region private fields
    _logger_: Logger = None
    # dictionary of the knowledge interactions used in the local service (
    _client_ki: Dict[str, KnowledgeInteraction] = PrivateAttr(default_factory=dict)
    _is_registered = False
    _is_ki_registered = False
    # dictionary of the knowledge interactions registered in the KE server
    _registered_ki_: Optional[Dict[str, KnowledgeInteraction]] = None
    # verify KE certificate if SSL is on
    _verify_cert_: bool = True
    # set True to let partially SUCCEEDED KI , set False to break when any of KI exchange is failed
    _partial_ki: bool = False
    # state of client
    _is_running_: bool = False
    _is_reconnecting_: bool = False
    _current_wait_timeout_: int = 30
    _http_timeout = (15, 180)
    _lock: RLock
    _registration_pending: bool = False

    # endregion

    def __init__(self, partial_ki: bool = False,
                 verify_cert: bool = ke_vars.VERIFY_SERVER_CERT, logger: Optional[Logger] = None, **kwargs):
        super().__init__(**kwargs)
        self._partial_ki = partial_ki
        self._verify_cert_ = verify_cert
        self._logger_ = logging.getLogger() if logger is None else logger
        self._client_ki = {}
        self._lock = RLock()

    # region ki meta

    @property
    def logger(self):
        return self._logger_

    @property
    def is_registered(self):
        return self._is_registered and self._is_ki_registered

    def get_registered_ki(self, ki_id: str):
        return self._registered_ki_[ki_id]

    def list_registered_ki(self):
        return self._registered_ki_.values()

    # endregion

    # region interaction utils
    def _assert_response_(self, response: requests.Response, ki_name: Optional[str] = None):
        """
        check if the response from the knowledge engine is correct
        :param response: response from KE
        :param ki_name: name of the method sending request to the KE
        :return:
        """
        ki_name = ki_name if ki_name is not None else "<none_gp_name>"
        if not response.ok:
            err = f"Invalid response for {ki_name}: {response.status_code}"
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
                self.reconnect(bg=True)
                raise Exception(f"KE error: {response.json()["message"]}")
            else:
                self.logger.error(f"Unknown {err}: {resp_content} ")

        assert response.ok
        try:
            resp_content = response.json()
        except Exception as err:
            if response.text == "":
                if ((response.url.startswith(self.ke_rest_endpoint))
                        and response.url[len(self.ke_rest_endpoint):] == 'sc/handle'):
                    # this is ok
                    pass
                else:
                    self.logger.warning(
                        f"Empty response for {ki_name} with status 'OK' (HTTP 200)." +
                        "Url: 'http://localhost:8280/rest/sc/handle'." +
                        "It's likely to be KE server issue. ")
            else:
                self.logger.warning(
                    f"{err}:  content is not JSON: {response.text}, ki: {ki_name}, url: {response.url} ")
            resp_content = {}
        if "exchangeInfo" in resp_content:
            exchange_info_list = resp_content["exchangeInfo"]
            if type(exchange_info_list) is not list:
                raise Exception(
                    f"Failed KI ({ki_name}) expected 'exchangeInfo' type is 'list' not '{type(exchange_info_list)}' ")
            has_success = False
            for exchange_info in exchange_info_list:
                kb_id = exchange_info["knowledgeBaseId"]
                if ExchangeInfoStatus.parse(exchange_info["status"]) == ExchangeInfoStatus.SUCCEEDED:
                    has_success = True
                if ExchangeInfoStatus.parse(exchange_info["status"]) == ExchangeInfoStatus.FAILED:
                    bindings = exchange_info["bindings"] if "bindings" in exchange_info else None
                    if not self._partial_ki:
                        raise Exception(
                            f"Failed KI({ki_name}, from: {kb_id}, status: {exchange_info["status"]}): " +
                            f"{exchange_info["failedMessage"]}, bindings:{bindings}")
                    else:
                        self.logger.error(
                            f"Failed KI({ki_name}, from: {kb_id}, status: {exchange_info["status"]}): " +
                            f"{exchange_info["failedMessage"]}, bindings:{bindings}")
            if not has_success and len(exchange_info_list) > 0:
                raise Exception(
                    f"Failed KI({ki_name},all exchanges have status: {ExchangeInfoStatus.FAILED}).  " +
                    f"From: {",".join([f'{exchange_info["knowledgeBaseId"]}:{exchange_info["failedMessage"]}'
                                       for exchange_info in exchange_info_list])}")

    # endregion

    # region registration/init
    def _register_procedure(self):
        try:
            self._is_ki_registered = False
            self._register_knowledge_base_()
            self._check_registered_ki_()
            self._is_ki_registered = True
        finally:
            self._registration_pending = False

    def register(self, bg=False):
        self._lock.acquire()
        if not self._is_registered and not self._registration_pending:
            self._registration_pending = True
            t = Thread(target=self._register_procedure)
            self._lock.release()
            t.start()
            if not bg:
                t.join()
        else:
            self._lock.release()
            # self._is_ki_registered = False
            # self._register_knowledge_base_()
            # self._check_registered_ki_()
            # self._is_ki_registered = True

    def _reconnect(self, timeout_s: int):
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

            is_connected = self._is_registered
        if is_connected:
            self.start()
        else:
            self.logger.error("Failed to reconnect")
        self._is_reconnecting_ = False

    def reconnect(self, timeout_s: int = 30, bg=False):
        self._lock.acquire()
        try:
            if self._is_reconnecting_:
                logging.info("Pending reconnect")
                return
            logging.info("Prepare reconnect")
            self._is_reconnecting_ = True
            self.stop()
            if bg:
                t = Thread(target=self._reconnect)
                t.start()
            else:
                self._reconnect(timeout_s=timeout_s)
        finally:

            self._lock.release()

    # region registration private

    def _assert_client_state_(self):
        if not self._is_registered:
            raise RuntimeError("Client is not registered")
        if not self.state():
            raise RuntimeError("Client is not running")

    def _register_knowledge_interaction_(self, ki: KnowledgeInteraction) -> str:
        if not self._is_registered:
            raise RuntimeError("Client is not registered")
        gp = ki.graph_pattern

        if ki.ki_type in [KnowledgeInteractionType.ASK, KnowledgeInteractionType.ANSWER]:
            graph_pattern_key = "graphPattern"
        else:
            graph_pattern_key = "argumentGraphPattern"
        prefixes = {**self.prefixes, **gp.prefixes_safe}
        body = {
            "knowledgeInteractionName": ki.ki_name,
            "knowledgeInteractionType": ki.ki_type.value,
            graph_pattern_key: gp.pattern_value,
            "prefixes": prefixes,
        }
        if gp.result_pattern is not None:
            body["resultGraphPattern"] = gp.result_pattern_value
        response = requests.post(
            self.ke_rest_endpoint + "sc/ki/",
            json=body,
            headers={"Knowledge-Base-Id": self.kb_id},
            verify=self._verify_cert_, timeout=self._http_timeout
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
        self._is_registered = False
        self.register(bg=False)

    def _check_registered_ki_(self):
        if self._registered_ki_ is None:
            'knowledgeInteractionName'
            # response = self._get_(endpoint=self.ke_rest_endpoint + "sc/ki/",
            # headers={"Knowledge-Base-Id": self.kb_id},     register=True)
            response = requests.get(
                self.ke_rest_endpoint + "sc/ki/",
                headers={"Knowledge-Base-Id": self.kb_id},
                verify=self._verify_cert_,
                timeout=self._http_timeout
            )
            if response.status_code == 200:
                for ki in response.json():
                    ki_name = ki["knowledgeInteractionName"]
                    ki_id = ki["knowledgeInteractionId"]
                    # TODO: optional override instead deleting and re registering
                    if ki_name in self._client_ki:
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
                for ki in self._client_ki.values():
                    self._register_knowledge_interaction_(ki)
            else:
                raise Exception(f"Can't check registered interactions, response: {response.status_code}")
                # self.logger.error("Can't check registered interactions")

    def _register_knowledge_base_(self):
        """
        Register a Knowledge Base with the given details at the given endpoint.
        """
        if self._is_registered:
            self.logger.warning(f"KB {self.kb_id} has been already registered")
            return

        self.logger.info(f"Start register KB: {self.kb_id} - {self.kb_name}")
        # response = self._get_(endpoint=self.ke_rest_endpoint + "sc/ki/", headers={"Knowledge-Base-Id": self.kb_id})
        response = requests.get(
            self.ke_rest_endpoint + "sc/ki/", headers={"Knowledge-Base-Id": self.kb_id},
            verify=self._verify_cert_,
            timeout=self._http_timeout
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
                verify=self._verify_cert_, timeout=self._http_timeout

            )
            # TODO handler error in response
            assert response.ok
            self.logger.info(f"KB registered:  {self.kb_id} - {self.kb_name}")
            self._is_registered = True
        elif response.status_code == HTTPStatus.BAD_REQUEST:
            raise Exception(f"KB registration {HTTPStatus.BAD_REQUEST}")
        elif response.status_code == HTTPStatus.OK:
            self.logger.info(f"KB is registered:  {self.kb_id} - {self.kb_name}")
            self._is_registered = True
        else:
            pass

    # endregion

    # endregion

    # region handlers and REST API utils

    # def _handler_wrapper_(self, ki_id: str,
    #                       handler: Optional[Callable[[str, Optional[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    #                       bindings: Optional[Dict[str, Any]] = None):
    #
    #     if handler is None:
    #         handler = default_handler
    #     self.logger.info(f"Handler arrived: {ki_id}")
    #     handler(ki_id=ki_id, bindings=bindings)
    #     # handler(ki_id=ki_id, bindings=bindings)

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
            self._handle_(bindings=result_bindings, ki_id=ki_id, handle_request_id=handle_request_id,
                          ki_type=ki.ki_type)
            return ki_id
        except Exception as ex:
            self.logger.error(
                f"Error occurred in handle_response kb_id:{self.kb_id} ki_id:{ki_id}, "
                f"status_code: {response.status_code} : {ex}")

    def _api_post_request_(self, endpoint: str, headers: Dict, ke_request: Union[Dict, List[dict[str, str]]],
                           register=False) -> Response:

        return self._http_request_wrapper(
            send_request=lambda: requests.post(endpoint, headers=headers, json=ke_request, verify=self._verify_cert_,
                                               timeout=self._http_timeout),
            endpoint=endpoint, register=register)

    def _api_get_request_(self, endpoint: str, headers: Dict, register=False) -> Response:
        return self._http_request_wrapper(
            send_request=lambda: requests.get(endpoint, headers=headers, verify=self._verify_cert_,
                                              timeout=self._http_timeout),
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

    def _handle_(self, bindings: list[dict[str, str]], ki_id: str, handle_request_id, ki_type: EnumItem):
        """
        REACT/ANSWER knowledge interactions handler, triggered by KE
        """
        ki_name = self._registered_ki_[ki_id].ki_name
        logging.info(f"HANDLE REQUEST={ki_id}:{ki_name}")
        post_json: dict
        if ki_type == KnowledgeInteractionType.REACT:
            post_json = {"handleRequestId": handle_request_id, "bindingSet": bindings, "resultBindingSet": bindings, }
        else:

            post_json = {"handleRequestId": handle_request_id, "bindingSet": bindings, }

        response = self._api_post_request_(endpoint=self.ke_rest_endpoint + "sc/handle",
                                           headers={"Knowledge-Base-Id": self.kb_id,
                                                    "Knowledge-Interaction-Id": ki_id, },
                                           ke_request=post_json, )

        self._assert_response_(response, ki_name=ki_name)
    # endregion
