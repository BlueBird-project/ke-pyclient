from abc import abstractmethod
from typing import List

from rdflib import Graph, Literal, Variable
from rdflib.namespace import XSD


# region utils

def is_variable(v):
    return (isinstance(v, str) and v.startswith("?")) or isinstance(v, Variable)


def infer_literal_datatype(literal: Literal):
    if literal.datatype:
        return literal.datatype

    py = literal.toPython()

    if isinstance(py, bool):
        return XSD.boolean

    if isinstance(py, int):
        return XSD.integer

    if isinstance(py, float):
        return XSD.double

    return XSD.string


# endregion


class GraphValidator:
    def __init__(self, ontology_graph: Graph):
        self.ontology_graph = ontology_graph

    @abstractmethod
    def validate_pattern(self, pattern_triples: List):
        pass
