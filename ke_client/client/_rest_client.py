import logging
from logging import Logger
from typing import Optional, List

import requests
from pydantic import TypeAdapter

import ke_client.ke_vars as ke_vars
from ke_client.ki_model import SmartClient, SCKnowledgeInteraction


class KERestClient:
    _logger_: Logger = None
    # verify KE certificate if SSL is on
    _verify_cert_: bool = True
    _http_timeout = (15, 180)
    ke_rest_endpoint: str

    def __init__(self, ke_rest_endpoint: str, verify_cert: bool = ke_vars.VERIFY_SERVER_CERT,
                 logger: Optional[Logger] = None):
        self._verify_cert_ = verify_cert
        self._logger_ = logging.getLogger() if logger is None else logger
        self.ke_rest_endpoint = ke_rest_endpoint

    @property
    def logger(self):
        return self._logger_

    def list_sc(self) -> List[SmartClient]:
        adapter = TypeAdapter(list[SmartClient])
        response = requests.get(
            self.ke_rest_endpoint + "sc", verify=self._verify_cert_, timeout=self._http_timeout
        )
        if response.status_code != 200:
            try:
                error_message = (f"GET sc list failed,status_code: {response.status_code}, "
                                 f"message: {response.content}")
            except Exception:
                error_message = f"Registration failed,status_code: {response.status_code}"
            raise Exception(error_message)
        sc_list = adapter.validate_json(response.content)
        return sc_list

    def get_sc_ki(self, kb_id: str) -> List[SCKnowledgeInteraction]:
        adapter = TypeAdapter(list[SCKnowledgeInteraction])
        response = requests.get(
            self.ke_rest_endpoint + "sc/ki", verify=self._verify_cert_, timeout=self._http_timeout,
            headers={"Knowledge-Base-Id": kb_id, }
        )
        if response.status_code != 200:
            try:
                error_message = (f"GET ki for {kb_id} failed,status_code: {response.status_code}, "
                                 f"message: {response.content}")
            except Exception:
                error_message = f"Registration failed,status_code: {response.status_code}"
            raise Exception(error_message)
        ki_list = adapter.validate_json(response.content)
        return ki_list
