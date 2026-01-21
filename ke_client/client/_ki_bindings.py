from typing import Dict, Any, Union, Optional, Callable

from pydantic import BaseModel, ConfigDict
from rdflib import URIRef, Literal
from rdflib.util import from_n3

from ._rdf_utils import is_nil, is_rdf_literal


# TODO: handle rdf graph prefixes
class BindingsBase(BaseModel):
    """
    KI binding object
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, bindings: Optional[Dict[str, Any]] = None, **kwargs):
        if bindings is None:
            bindings = kwargs
            kwargs = {}
        rdf_nodes = {k: v.default for k, v in self.model_fields.items() if not v.is_required()}
        rdf_nodes.update({k: from_n3(str(v)) if (type(v) is str or type(v) is float or type(v) is int) else v
                          for k, v in bindings.items()})
        # rdf_literals = {k: v for k, v in self.__class__.__annotations__.items() if is_rdf_literal(v)}
        for k, rdf_node in rdf_nodes.items():
            if type(rdf_node) is URIRef:
                is_literal, is_optional = is_rdf_literal(self.__class__.__annotations__.get(k))
                is_node_nil = is_nil(rdf_node)
                if is_literal and not is_node_nil:
                    raise Exception(f"Non nil URIRef not allowed for: {k} in {self.__class__.__name__}")
                if is_node_nil:
                    if is_literal and is_optional:
                        rdf_nodes[k] = None
                    # else:
                    #     pass
        super().__init__(**rdf_nodes, **kwargs)

    def n3(self, skip_none: bool = True) -> Dict[str, str]:
        """

        :param skip_none:  skip None values
        :return:
        """
        if skip_none:
            return {k: v.n3() if (type(v) is Literal or type(v) is URIRef) else str(v)
                    for k, v in self.__dict__.items() if v is not None}
        return {k: v.n3() if (type(v) is Literal or type(v) is URIRef) else str(v)
                for k, v in self.__dict__.items()}

    @property
    def input_bindings(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def binding_keys(cls) -> list:
        return cls.model_fields.keys()

    # @staticmethod
    # def get_value(attr: Union[Literal, URIRef]) -> Optional[str]:
    #     if type(attr) is Literal:
    #         return attr.value
    #     elif is_nil(attr):
    #         return None
    #     else:
    #         raise ValueError(f"Invalid value {attr}. Expected {Literal.__module__}.{Literal.__name__}. ")

    @staticmethod
    def convert_value(attr: Union[Literal, URIRef, None], converter: Callable[[str], Optional[Any]] = str) \
            -> Optional[Any]:
        """
        safe convert Literal (or rdf:nil type:URIRef) value
        :param attr: Literal instance
        :param converter: converter callable
        :return: result of converter(value)  or None
        """
        if attr is None:
            return None
        if type(attr) is Literal:
            return converter(attr.value)
        elif is_nil(attr):
            return None
        else:
            raise ValueError(f"Invalid value {attr}. Expected {Literal.__module__}.{Literal.__name__}. ")

    def output_bindings(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}
    # def output_bindings(self, input_bindings) -> dict:
    #     return {k: v for k, v in self.__dict__.items() if v is not None}
