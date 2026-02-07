from abc import abstractmethod
from typing import Union, List, Dict, TypeAlias

from ke_client.ki_model import KIPostResponse, KIAskResponse

KERequest: TypeAlias = Union[Dict, List[dict[str, str]]]


class KERequestClient:
    @abstractmethod
    def ask_ke(self, bindings: KERequest, ki_id: str, ki_name: str) -> KIAskResponse:
        """
        ASK for knowledge with query bindings to receive bindings for an ASK knowledge interaction.
        """
        pass

    @abstractmethod
    def post_ke(self, bindings: KERequest, ki_id: str, ki_name: str) -> KIPostResponse:
        """
        POST knowledge interactions - post bindings for defined graph pattern
        """
        pass
