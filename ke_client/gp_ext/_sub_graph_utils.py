import logging
import re
from typing import List, Dict, Tuple, Optional

from ke_client import rdf_nil
from rdflib import Graph, Namespace, RDF, OWL, RDFS, XSD
from rdflib.term import Variable, URIRef, Literal

_DEFAULT_PREFIX_MAP = {
    "rdf": RDF,  # Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    "rdfs": RDFS,  # Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    "xsd": XSD,
    "owl": OWL,
    "saref": Namespace("https://saref.etsi.org/core/"),
    "foaf": Namespace("http://xmlns.com/foaf/0.1/"),
    # "ubmarket": Namespace("https://ubflex.bluebird.eu/market/"),
}


def _match_term(t1, t2, mapping):
    # t1 from small graph, t2 from large graph
    if isinstance(t1, Variable):
        if t1 in mapping:
            return mapping[t1] == t2
        else:
            mapping[t1] = t2
            return True
    else:
        if isinstance(t2, Variable):
            # TODO: this could be more efficient (online list filtering)
            t1_list = [k for k, v in mapping.items() if v == t2]
            if len(t1_list) == 0:
                mapping[t1] = t2
                return True
            elif len(t1_list) == 1:
                return t1 == t1_list[0]
            else:
                logging.info(f"variable: {t2} has more than one mapping .")
                return False
            # if t1 in mapping:
            #     return mapping[t1] == t2
            # else:
            #     mapping[t1] = t2
            #     return True

        return t1 == t2


def triple_subgraph_check(ask_triples: List[Tuple], answer_triple: List[Tuple]):
    return is_subgraph_pattern(ask_triples, answer_triple)


def is_subgraph_pattern(g_small, g_large):
    """
    Check if g_small is a subgraph of g_large (both contain variables)
    using graph homomorphism.
    """

    def match_triples(i, mapping):
        # All triples matched
        if i == len(g_small):
            return True
        s1, p1, o1 = g_small[i]

        for s2, p2, o2 in g_large:
            new_mapping = mapping.copy()

            if _match_term(s1, s2, new_mapping) and \
                    _match_term(p1, p2, new_mapping) and \
                    _match_term(o1, o2, new_mapping):

                if match_triples(i + 1, new_mapping):
                    return True

        return False

    res = match_triples(0, {})

    return res


def extract_new_triples(g_small, g_large, allow_extra_knowledge=False):
    """
    Check if g_small is a subgraph of g_large (both contain variables)
    using graph homomorphism.
    """
    all_mapping = {}
    new_triples = []

    def match_triples(i, mapping):
        # All triples matched
        if i == len(g_small):
            return True
        s1, p1, o1 = g_small[i]
        is_new_triple = True
        for s2, p2, o2 in g_large:
            new_mapping = mapping.copy()

            if _match_term(s1, s2, new_mapping) and \
                    _match_term(p1, p2, new_mapping) and \
                    _match_term(o1, o2, new_mapping):
                is_new_triple = False
                if isinstance(s1, Variable):
                    all_mapping[s1] = s2
                if isinstance(o1, Variable):
                    all_mapping[o1] = o2
                # mapping = new_mapping
                # print(f"matched triple {i}: {s1}/{s2} {p1} {o1}/{o2}")
                if match_triples(i + 1, new_mapping):
                    # all_mapping.update(**mapping)
                    return True
        if is_new_triple:
            # print(f"new triple {i}: {s1} {p1} {o1}")
            new_triples.append((s1, p1, o1))
        return match_triples(i + 1, mapping)
        # return True

    res = match_triples(0, {})
    new_triple_map = {}
    if res:
        for s, p, o in new_triples:
            if s in all_mapping:
                if o in all_mapping:
                    logging.warning(
                        f"Both subject and object ({(s, p, o)}) exist in both graphs, is extra relation required ? ")
                else:
                    if not isinstance(o, Variable) and (s in all_mapping and s not in new_triple_map):
                        if not allow_extra_knowledge:
                            return None, None, None
                        all_mapping[o] = o
                        new_triple_map[o] = o
                    else:
                        all_mapping[o] = rdf_nil
                        new_triple_map[o] = rdf_nil
            elif o in all_mapping:
                if not isinstance(o, Variable):
                    if not allow_extra_knowledge:
                        return None, None, None
                if all_mapping[o] != rdf_nil:
                    # check   new triple : if subject is rdf nil and object is not rdf_nil return None
                    return None, None, None

                all_mapping[s] = rdf_nil
                new_triple_map[s] = rdf_nil
            else:
                # separated triple from the graph
                if not allow_extra_knowledge:
                    return None, None, None
    return new_triples, new_triple_map, all_mapping


def process_pattern(pattern_str, prefix_str: Optional = "", extend=False, ontology_files: List[str] = None):
    g = Graph()

    # Pre-processing: Turtle parser doesn't like naked '?' variables.
    # We temporarily replace '?var' with '<var:var>' to allow standard parsing.
    grounded_str = re.sub(r'\?(\w+)', r'<var:\1>', pattern_str)

    # Parse as Turtle to handle the semicolon (;) and Datatypes (^^)
    g.parse(data=prefix_str + "\n" + grounded_str, format="turtle")
    if extend:
        if ontology_files is None:
            from ke_client import ke_settings
            ontology_files = ke_settings.extension_ontology_files
        for ttl_file in ontology_files:
            g.parse(ttl_file, format="turtle")
    return g


def matches_pattern(in_graph, query):
    # Convert the pattern string into a SPARQL ASK query
    # This is the most efficient way to check if a graph fits a pattern
    # query = f"ASK {{ {pattern_str} }}"
    # print(in_graph.query(select_pattern).bindings)
    return bool(in_graph.query(query))


# todo

def get_ask(ask_pattern, prefixes: Dict[str, str] = None) -> str:
    if prefixes is None:
        prefixes = _DEFAULT_PREFIX_MAP
    prefix_str = "\n".join([f"PREFIX {k}:<{v}>" for k, v in prefixes.items()])
    return f"""   {prefix_str}
    ASK {{ {ask_pattern} }}"""


# region turtle parsing

# region helpers
# -------------------------
# Term parsing
# -------------------------

def _parse_term(token: str, prefixes: Dict[str, str] = None):
    if prefixes is None:
        prefixes = _DEFAULT_PREFIX_MAP
    token = token.strip()

    # -------------------------
    # Variable
    # -------------------------
    if token.startswith("?"):
        return Variable(token[1:])

    # -------------------------
    # Typed literal "..."^^datatype
    # -------------------------
    if token.startswith('"'):
        # Find end of literal safely
        end_quote = token.rfind('"')
        if end_quote == -1:
            raise ValueError(f"Invalid literal: {token}")

        value = token[1:end_quote]
        rest = token[end_quote + 1:].strip()

        # Typed literal
        if rest.startswith("^^"):
            dtype_token = rest[2:].strip()
            datatype = _parse_term(dtype_token, prefixes=prefixes)
            return Literal(value, datatype=datatype)

        # Plain literal
        return Literal(value)

    # -------------------------
    # IRI <...>
    # -------------------------
    if token.startswith("<") and token.endswith(">"):
        return URIRef(token[1:-1])

    # -------------------------
    # Prefixed name
    # -------------------------
    if ":" in token:
        prefix, local = token.split(":", 1)
        if prefix in prefixes:
            return prefixes[prefix][local]

    # -------------------------
    # Fallback
    # -------------------------
    return URIRef(token)


# -------------------------
# Split safely on '.'
# -------------------------
def _split_statements(text: str):
    statements = []
    buf = []

    in_iri = False
    in_literal = False

    for c in text:
        if c == "<" and not in_literal:
            in_iri = True
        elif c == ">" and in_iri:
            in_iri = False
        elif c == '"' and not in_iri:
            in_literal = not in_literal

        # triple separator
        if c == "." and not in_iri and not in_literal:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(c)

    # remaining buffer
    rest = "".join(buf).strip()
    if rest:
        statements.append(rest)

    return statements


# -------------------------
# Split safely on ';'
# -------------------------
def _split_predicates(statement: str):
    parts = []
    buf = []

    in_iri = False
    in_literal = False

    for c in statement:
        if c == "<" and not in_literal:
            in_iri = True
        elif c == ">" and in_iri:
            in_iri = False
        elif c == '"' and not in_iri:
            in_literal = not in_literal

        if c == ";" and not in_iri and not in_literal:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(c)

    rest = "".join(buf).strip()
    if rest:
        parts.append(rest)

    return parts


# -------------------------
# Split safely on ','
# -------------------------
def _split_objects(obj_str: str):
    parts = []
    buf = []

    in_iri = False
    in_literal = False

    for c in obj_str:
        if c == "<" and not in_literal:
            in_iri = True
        elif c == ">" and in_iri:
            in_iri = False
        elif c == '"' and not in_iri:
            in_literal = not in_literal

        if c == "," and not in_iri and not in_literal:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(c)

    rest = "".join(buf).strip()
    if rest:
        parts.append(rest)

    return parts


# endregion

def parse_turtle_pattern(pattern: str, prefixes: Dict[str, Namespace] = None):
    triples = []

    statements = _split_statements(pattern)

    for stmt in statements:
        predicate_parts = _split_predicates(stmt)

        current_subject = None

        for i, part in enumerate(predicate_parts):

            if i == 0:
                tokens = part.split(None, 2)
                if len(tokens) != 3:
                    raise ValueError(f"Invalid triple: {part}")
                s, p, o = tokens
                current_subject = _parse_term(s, prefixes=prefixes)
            else:
                tokens = part.split(None, 1)
                if len(tokens) != 2:
                    raise ValueError(f"Invalid predicate-object: {part}")
                p, o = tokens

            predicate = _parse_term(p, prefixes=prefixes)

            for obj in _split_objects(o):
                triples.append((
                    current_subject,
                    predicate,
                    _parse_term(obj, prefixes=prefixes)
                ))

    return triples


# endregion
def pretty_str(gp_str: str):
    return gp_str.replace(" .", " .\n")
