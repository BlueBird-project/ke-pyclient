import os
from typing import List, Dict, Set, Union, Optional

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal, Variable, BNode
from rdflib.collection import Collection
from rdflib.namespace import XSD
from collections import defaultdict

from ke_client.validation._gp_validator import GraphValidator, infer_literal_datatype, is_variable


# region utils

def _build_variable_types(pattern):
    var_types = defaultdict(set)
    for s, p, o in pattern:
        if p == RDF.type:
            if is_variable(s):
                var_types[s].add(o)
    return var_types


# endregion

# region init standard graph predicates/resources
CLASS_TYPES = {
    OWL.Class,
    RDFS.Class,
    RDFS.Datatype,
}
_known_resources = {
    # RDF
    RDF.type,
    RDF.Property,

    # RDFS
    RDFS.Class,
    RDFS.Resource,
    RDFS.Literal,
    RDFS.Datatype,
    RDFS.subClassOf,
    RDFS.domain,
    RDFS.range,

    # OWL
    OWL.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,

    # XSD
    XSD.string,
    XSD.integer,
    XSD.int,
    XSD.float,
    XSD.double,
    XSD.boolean,
    XSD.decimal,
    XSD.date,
    XSD.dateTime,
    XSD.time,
    XSD.duration,
    XSD.anyURI,
}
_known_classes = {
    RDFS.Class,
    OWL.Class,
    RDFS.Datatype,
}
_known_properties = {
    RDF.type,
    RDFS.subClassOf,
    RDFS.domain,
    RDFS.range,
}


# _known_xsd_types = {
#     XSD.string,
#     XSD.integer,
#     XSD.int,
#     XSD.float,
#     XSD.double,
#     XSD.boolean,
#     XSD.decimal,
#     XSD.date,
#     XSD.dateTime,
#     XSD.time,
#     XSD.duration,
#     XSD.anyURI,
# }


# endregion

class SimpleValidator(GraphValidator):
    # region fields/init
    known_classes: Set
    known_properties: Set
    known_resources: Set
    object_properties: Set
    datatype_properties: Set
    property_domains: Dict
    property_ranges: Dict

    def __init__(self, ontology_graph: Graph):
        super().__init__(ontology_graph=ontology_graph)
        self.known_classes = set()
        self.known_properties = set()
        self.known_resources = set()
        self.object_properties = set()
        self.datatype_properties = set()
        self.property_domains = {}
        self.property_ranges = {}
        self._init_indexes()
        self.known_classes.update(_known_classes)
        self.known_properties.update(_known_properties)
        self.known_resources.update(_known_resources)

    @staticmethod
    def load(turtle_files: Optional[List[str]] = None):
        if turtle_files is None:
            from ke_client import ke_settings
            ontology_path = ke_settings.validation_ontology_path
            if ontology_path is None:
                raise ValueError("'validation_ontology_path' is not defined")
            turtle_files = [os.path.join(ontology_path, fn) for fn in os.listdir(ontology_path) if fn.endswith(".ttl")]

        ontology_graph = Graph()
        for ttl_file_path in turtle_files:
            ontology_graph.parse(ttl_file_path, format="turtle")
        return SimpleValidator(ontology_graph=ontology_graph)

    def _init_indexes(self):
        self.subclass_map = defaultdict(set)

        for s, p, o in self.ontology_graph:
            self.known_resources.add(s)
            self.known_resources.add(o)
            # classes
            if p == RDF.type and o in CLASS_TYPES:
                self.known_classes.add(s)
            # if (s, RDF.type, OWL.Class) in self.ontology_graph:
            #     self.known_classes.add(s)

            # properties
            if (s, RDF.type, OWL.ObjectProperty) in self.ontology_graph:
                self.known_properties.add(s)
                self.object_properties.add(s)

            if (s, RDF.type, OWL.DatatypeProperty) in self.ontology_graph:
                self.known_properties.add(s)
                self.datatype_properties.add(s)
            if (s, RDF.type, RDF.Property) in self.ontology_graph:
                self.known_properties.add(s)

            # domain/range
            if p == RDFS.domain:
                if isinstance(o, BNode):
                    self.property_domains[s] = list(
                        Collection(self.ontology_graph, self.ontology_graph.value(o, OWL.unionOf)))
                else:
                    self.property_domains[s] = o
            if p == RDFS.range:
                if isinstance(o, BNode):
                    self.property_ranges[s] = list(
                        Collection(self.ontology_graph, self.ontology_graph.value(o, OWL.unionOf)))
                else:
                    self.property_ranges[s] = o
                    # subclass
            if p == RDFS.subClassOf:
                self.subclass_map[s].add(o)

    # endregion

    def _assert_node_type(self, node_type: URIRef, expected_type: Union[List, URIRef, BNode] ):
        if type(expected_type) is list:
            if node_type in expected_type:
                return True
        elif node_type == expected_type:
            return True
        visited = set()
        stack = [node_type]
        while stack:
            current = stack.pop()
            if type(expected_type) is list:
                if current in expected_type:
                    return True
            elif current == expected_type:
                return True
            if current in visited:
                continue
            visited.add(current)
            # check if one of parent classes matches expected type
            for superclass in self.subclass_map.get(current, []):
                stack.append(superclass)
        return False

    def validate_pattern(self, pattern_triples: List):
        errors = []
        variable_types = _build_variable_types(pattern_triples)

        for s, p, o in pattern_triples:
            # --------------------------------------------------
            # rdf:type validation
            # --------------------------------------------------
            if p == RDF.type and not is_variable(o):
                if o not in self.known_classes:
                    errors.append(f"Unknown class: {o}")
                continue
            # --------------------------------------------------
            # predicate existence
            # --------------------------------------------------
            if p not in self.known_properties:
                errors.append(f"Unknown predicate: {p}")
                continue
            # --------------------------------------------------
            # subject URI existence   (TODO: optional ?)
            # --------------------------------------------------
            if isinstance(s, URIRef):
                if s not in self.known_resources:
                    errors.append(f"Unknown subject: {s}")
            # --------------------------------------------------
            # object URI existence
            # --------------------------------------------------
            if isinstance(o, URIRef):
                if o not in self.known_resources:
                    errors.append(f"Unknown object: {o}")
            # --------------------------------------------------
            # property kind consistency
            # --------------------------------------------------
            if p in self.datatype_properties:
                if not isinstance(o, Literal) and not isinstance(o, Variable):
                    errors.append(f"{p} expects literal object")
            if p in self.object_properties:
                if isinstance(o, Literal):
                    errors.append(f"{p} expects URI/variable object")
            # --------------------------------------------------
            # rdf domain validation
            # --------------------------------------------------
            expected_domain = self.property_domains.get(p)
            if expected_domain:
                if is_variable(s):
                    subject_types = variable_types.get(s, set())
                    if subject_types:
                        # todo:

                        valid = any(self._assert_node_type(node_type=subject_type, expected_type=expected_domain)
                                    for subject_type in subject_types)
                        if not valid:
                            errors.append(f"Domain violation {p}: {s} must be {expected_domain} ")

            # --------------------------------------------------
            # range validation
            # --------------------------------------------------
            expected_range = self.property_ranges.get(p)
            if expected_range:

                # literal
                if isinstance(o, Literal):
                    actual_type = infer_literal_datatype(o)
                    if actual_type != expected_range:
                        errors.append(f"Range violation {p}: {o} must be {expected_domain}, got: {actual_type}")
                elif is_variable(o):
                    # variable object
                    object_types = variable_types.get(o, set())
                    if object_types:
                        valid = any(self._assert_node_type(node_type=object_type, expected_type=expected_range)
                                    for object_type in object_types)
                        if not valid:
                            errors.append(f"Range violation {p}: {o} must be {expected_range} ")
                elif isinstance(o, URIRef):
                    # URI object
                    pass

        return errors
