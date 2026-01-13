from typing import Optional, get_origin, get_args, Union

from rdflib import URIRef, Literal

nil = URIRef("#nil", base="http://www.w3.org/1999/02/22-rdf-syntax-ns")
# just an alias
rdf_nil = nil


def is_nil(uri_ref: Optional[URIRef]):
    if uri_ref is None:
        return False
    return (uri_ref.fragment == rdf_nil.fragment and str(uri_ref.defrag()) == str(rdf_nil.defrag())) \
        or str(uri_ref) == "rdf:nil"


def is_rdf_literal(field_type):
    origin = get_origin(field_type)
    args = get_args(field_type)
    if origin is Union:
        for t in args:
            if t is Literal:
                return True, type(None) in args
        return False, type(None) in args
    else:
        return field_type is Literal, False
