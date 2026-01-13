import re
from typing import Optional, Union, Callable, List, Dict, Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from ke_client.utils import time_utils
from ke_client.utils.enum_utils import EnumUtils

RDF_BINDING_REGEX = r"\?[A-Za-z_][A-Za-z0-9_]+"
rdf_binding_pattern = re.compile(RDF_BINDING_REGEX)


class GraphPattern(BaseSettings):
    name: str = Field(...)
    prefixes: Optional[dict] = None
    description: Optional[str] = None
    pattern: List[str]
    result_pattern: Optional[List[str]] = None
    required_bindings: Optional[List[str]] = None
    #
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)

    @property
    def prefixes_safe(self) -> Dict:
        return self.prefixes if self.prefixes is not None else {}

    @property
    def pattern_value(self) -> str:
        return "\n ".join(self.pattern)

    @property
    def result_pattern_value(self) -> Optional[str]:
        if self.result_pattern is not None:
            return "\n ".join(self.result_pattern)
        return None

    def verify_bindings(self, bindings: Dict[str, Any]):
        if self.required_bindings is None:
            return
        for binding_key in self.required_bindings:
            if bindings is None:
                raise KeyError(f"Binding key={binding_key} missing in {self.result_pattern}. ")
            if binding_key not in bindings:
                raise KeyError(f"Binding key={binding_key} missing in {self.result_pattern}. ")

    @property
    def pattern_vars(self) -> List[str]:
        # k[1:] -> skip sign '?'
        return [k[1:] for k in rdf_binding_pattern.findall(self.pattern_value)]

    @property
    def result_pattern_vars(self) -> List[str]:
        if self.result_pattern_value is None:
            return []
        # k[1:] -> skip sign '?'
        return [k[1:] for k in rdf_binding_pattern.findall(self.result_pattern_value)]

    def get_result_pattern_bindings(self, result_binding_set: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result_vars = self.result_pattern_vars
        for v in result_vars:
            if v not in result_binding_set:
                return None
        # all required variables are in the result set
        # TODO: verify if variables names can be switched in the result binding set
        return {k: v for k, v in result_binding_set.items() if k in self.result_pattern_vars}


class KnowledgeInteractionType(EnumUtils):
    POST = "PostKnowledgeInteraction"
    ASK = "AskKnowledgeInteraction"
    REACT = "ReactKnowledgeInteraction"
    ANSWER = "AnswerKnowledgeInteraction"


class ExchangeInfoStatus(EnumUtils):
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class KnowledgeInteraction(BaseModel):
    name: str
    handler: Union[
        Callable[[str, Optional[List[Dict[str, Any]]]], Union[Dict[str, Any], List[Dict[str, Any]]]],
        Callable[[], Union[Dict[str, Any], List[Dict[str, Any]]]],
        None
    ] = None
    type: str
    graph_pattern: GraphPattern
    # _is_registered_: bool = False
    _ki_id_: Optional[str] = None

    @property
    def ki_id(self):
        # raise exception if ki_id is None
        return self._ki_id_

    @ki_id.setter
    def ki_id(self, value):
        self._ki_id_ = value

    @ki_id.deleter
    def ki_id(self):
        del self._ki_id_


class PostExchangeInfo(BaseModel):
    argumentBindingSet: List[Dict[str, Any]]
    resultBindingSet: List[Dict[str, Any]]
    initiator: Optional[str] = None
    knowledgeBaseId: str
    knowledgeInteractionId: str
    exchangeStart: str
    status: str

    @property
    def exchange_start_ms(self):
        return time_utils.xsd_to_ts(self.exchangeStart)

    @property
    def exchange_end_ms(self):
        return time_utils.xsd_to_ts(self.exchangeEnd)


class AskExchangeInfo(BaseModel):
    bindingSet: List[Dict[str, Any]]
    initiator: Optional[str] = None
    knowledgeBaseId: str
    knowledgeInteractionId: str
    exchangeStart: str
    status: str

    @property
    def exchange_start_ms(self):
        return time_utils.xsd_to_ts(self.exchangeStart)

    @property
    def exchange_end_ms(self):
        return time_utils.xsd_to_ts(self.exchangeEnd)


class KIPostResponse(BaseModel):
    resultBindingSet: List[Dict[str, Any]]
    exchangeInfo: List[PostExchangeInfo]

    @property
    def result_binding_set(self):
        if len(self.resultBindingSet) > 0:
            return self.resultBindingSet
        accu: List = []
        for ei in self.exchangeInfo:
            accu += ei.resultBindingSet
        return accu


class KIAskResponse(BaseModel):
    bindingSet: List[Dict[str, Any]]
    exchangeInfo: List[AskExchangeInfo]

    @property
    def binding_set(self):
        if len(self.bindingSet) > 0:
            return self.bindingSet
        accu: List = []
        for ei in self.exchangeInfo:
            accu += ei.bindingSet
        return accu

#  [ {dict: 8} {'argumentBindingSet': [{'ts_date_from': '"1970-01-01T00:00:00.001000+00:00"', 'ts_date_to': '"2057-08-16T11:23:02+00:00"', 'ts_interval_uri': '<http://ke.bluebird.com/interval/1/2765186582000>'}], 'exchangeEnd': '2025-12-18T18:23:24.584+00:00', 'exchangeStart': '2025-12-18T18:23:24.574+00:00', 'initiator': 'knowledgeBase', 'knowledgeBaseId': 'http://fm.bluebird.com', 'knowledgeInteractionId': 'http://fm.bluebird.com/interaction/react-fm-ts-info-request', 'resultBindingSet': [{'time_create': '"2025-12-18T18:23:24.578000+00:00"', 'ts_interval_uri': '<http://ke.bluebird.com/interval/1/2765186582000>', 'ts_uri': '<http://fm.bluebird.com/ts/1/2765186582000/60/0>', 'ts_usage': '<s4ener:Consumption>'}], 'status': 'SUCCEEDED'}
# 'initiator' = {str} 'knowledgeBase'
# 'knowledgeBaseId' = {str} 'http://fm.bluebird.com'
# 'knowledgeInteractionId' = {str} 'http://fm.bluebird.com/interaction/react-fm-ts-info-request'
# 'exchangeStart' = {str} '2025-12-18T18:23:24.574+00:00'
# 'exchangeEnd' = {str} '2025-12-18T18:23:24.584+00:00'
# 'status' = {str} 'SUCCEEDED'
# 'argumentBindingSet' = {list: 1} [{'ts_date_from': '"1970-01-01T00:00:00.001000+00:00"', 'ts_date_to': '"2057-08-16T11:23:02+00:00"', 'ts_interval_uri': '<http://ke.bluebird.com/interval/1/2765186582000>'}]
# 'resultBindingSet' = {list: 1} [{'time_create': '"2025-12-18T18:23:24.578000+00:00"', 'ts_interval_uri': '<http://ke.bluebird.com/interval/1/2765186582000>', 'ts_uri': '<http://fm.bluebird.com/ts/1/2765186582000/60/0>', 'ts_usage': '<s4ener:Consumption>'}]
# ]
