import logging
import time
from typing import List, Tuple, Dict, Any, Optional, Union, Callable

from ke_client.gp_ext._model import GraphPatternExtMode
from ke_client.gp_ext._sub_graph_utils import parse_turtle_pattern, process_pattern, get_ask, matches_pattern, \
    extract_new_triples, is_subgraph_pattern, triple_subgraph_check
from ke_client.ki_model import SCKnowledgeInteraction, KnowledgeInteractionType, SCKnowledgeInteractionBase, \
    GraphPattern, SmartClient, KnowledgeInteraction
from rdflib import Graph, Node, Namespace, RDF, RDFS, XSD, OWL


class KIPattern:
    kb_id: str
    ki_name: str
    graph_pattern: str
    interaction_type: str
    _ki_id: Optional[str] = None
    _prefixes: Dict[str, Namespace]
    _triples: List[Tuple[Node, Node, Node]] = None
    _processed_pattern: Graph = None
    _extended_pattern: Graph = None
    ext_new_triples: List[Tuple[Node, Node, Node]] = None
    _ext_new_mapping: Optional[Dict[Node, Node]] = None
    _ext_all_mapping: Optional[Dict[Node, Node]] = None
    ext_gp_id: Optional[str] = None

    def __repr__(self):
        return f"{self.kb_id}:{self.ki_name}"

    def __init__(self, kb_id: str, ki_name: str, interaction_type: str, graph_pattern: str,
                 ki_id: Optional[str] = None):
        self.kb_id = kb_id
        self.ki_name = ki_name
        self.interaction_type = interaction_type
        self.graph_pattern = graph_pattern
        self._ki_id = ki_id
        default_prefixes = {
            "rdf": RDF,
            "rdfs": RDFS,  # Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
            "xsd": XSD,
            "owl": OWL,
            # "saref": Namespace("https://saref.etsi.org/core/"),
            # "foaf": Namespace("http://xmlns.com/foaf/0.1/"),
            # "ubmarket": Namespace("https://ubflex.bluebird.eu/market/"),
        }
        from ke_client import ke_settings
        if ke_settings.ontology_prefixes:
            default_prefixes.update({k: Namespace(v) for k, v in ke_settings.ontology_prefixes.items()})

    @property
    def triples(self) -> List[Tuple[Node, Node, Node]]:
        if self._triples is None:
            self._triples = parse_turtle_pattern(self.graph_pattern)
        return self._triples

    @property
    def processed_pattern(self):
        if self._processed_pattern is None:
            self._processed_pattern = process_pattern(self.graph_pattern, extend=False)
        return self._processed_pattern

    @property
    def extended_pattern(self):
        if self._extended_pattern is None:
            self._extended_pattern = process_pattern(self.graph_pattern, extend=True)
        return self._extended_pattern

    @property
    def sparql_ask(self):
        return get_ask(self.graph_pattern)

    def set_new_triples(self, ki_id: str, new_triples: Tuple, mapping: Dict[Node, Node], new_mapping: Dict[Node, Node]):
        # noinspection PyTypeChecker
        self.ext_new_triples = new_triples
        self._ext_all_mapping = mapping
        self._ext_new_mapping = new_mapping
        self.ext_gp_id = ki_id

    @property
    def graph_pattern_new(self) -> str:
        g = Graph()
        for t in self.triples:
            g.set(t)
        for t in self.ext_new_triples:
            _t = tuple([self._ext_all_mapping[s] if s in self._ext_all_mapping else s for s in t])
            # noinspection PyTypeChecker
            g.set(_t)
        g.namespace_manager.reset()
        return g.serialize(format="nt")

    @property
    def graph_pattern_ext(self) -> str:
        g = Graph()
        for t in self.ext_new_triples:
            _t = tuple([self._ext_all_mapping[s] if s in self._ext_all_mapping else s for s in t])
            # noinspection PyTypeChecker
            g.set(_t)
        g.namespace_manager.reset()
        return g.serialize(format="nt")

    @property
    def ki_id(self):
        if self._ki_id is None:
            return f"{self.kb_id}/{self.ki_name}"
        return self._ki_id


class SemanticExt:
    # region fields
    class KBCache:
        kb_id: str
        ki_patterns: Dict[str, KIPattern]

        def __init__(self, kb_id: str, ki_patterns: Optional[Dict[str, KIPattern]] = None):
            self.kb_id = kb_id
            if ki_patterns is None:
                self.ki_patterns = {}
            else:
                self.ki_patterns = ki_patterns

        # def __setitem__(self, key: SCKnowledgeInteractionBase, value: KIPattern):
        #     if key.knowledge_interaction_name not in self.ki_patterns:
        #         raise KeyError(f"Duplicate KBCache key {key.knowledge_interaction_name}")
        #     self.ki_patterns[key.knowledge_interaction_name] = value

        def __getitem__(self, ki: Union[SCKnowledgeInteractionBase, SCKnowledgeInteraction]) -> KIPattern:
            if ki.knowledge_interaction_name not in self.ki_patterns:
                if type(ki) is SCKnowledgeInteractionBase:
                    ki_id = None
                else:
                    ki_id = ki.knowledge_interaction_id
                self.ki_patterns[ki.knowledge_interaction_name] \
                    = KIPattern(kb_id=self.kb_id,
                                ki_name=ki.knowledge_interaction_name,
                                interaction_type=ki.knowledge_interaction_type,
                                graph_pattern=ki.graph_pattern, ki_id=ki_id)
            return self.ki_patterns[ki.knowledge_interaction_name]

        def set_item(self, ki: SCKnowledgeInteractionBase) -> KIPattern:

            return self[ki]

        # def set_gp(self, gp: GraphPattern, ki_type: str):
        #     sc_ki = gp.init_sc_ki(ki_type=ki_type)
        #     self[sc_ki] = KIPattern(kb_id=self.kb_id,
        #                             ki_name=sc_ki.knowledge_interaction_name,
        #                             interaction_type=sc_ki.knowledge_interaction_type,
        #                             graph_pattern=sc_ki.graph_pattern)

    ki_cache: Dict[str, KBCache]
    kb_id: str
    _sc_list: List[SmartClient] = None

    def __init__(self, kb_id: str):
        # , ki_list: Optional[List[SCKnowledgeInteraction]] = None):
        self.kb_id = kb_id
        self.ki_cache = {kb_id: SemanticExt.KBCache(kb_id=kb_id, ki_patterns={})}

    # def __init__(self, kb_id: str, ki_list: List[SCKnowledgeInteraction], only_answer_ki=True):
    #     self.kb_id = kb_id
    #     if only_answer_ki:
    #         self.ki_cache = {kb_id: SemanticExt.KBCache(kb_id=kb_id, ki_patterns={
    #             ki.knowledge_interaction_name: KIPattern(kb_id=kb_id, ki_name=ki.knowledge_interaction_name,
    #                                                      interaction_type=ki.knowledge_interaction_type,
    #                                                      graph_pattern=ki.graph_pattern) for ki in ki_list
    #             if ki.knowledge_interaction_type == KnowledgeInteractionType.ANSWER
    #         })}
    #     else:
    #         self.ki_cache = {kb_id: SemanticExt.KBCache(kb_id=kb_id, ki_patterns={
    #             ki.knowledge_interaction_name: KIPattern(kb_id=kb_id, ki_name=ki.knowledge_interaction_name,
    #                                                      interaction_type=ki.knowledge_interaction_type,
    #                                                      graph_pattern=ki.graph_pattern) for ki in ki_list
    #         })}

    # def get_instance(self, kb_id: str):
    #     KBCache
    #     self.kb_id = kb_id
    #     self.ki_cache = {kb_id: SemanticExt.KBCache(kb_id=kb_id, ki_patterns={})}

    def set_ki(self, gp: GraphPattern, ki_type: str):
        # TODO: check if similar graph pattern does not already exists
        if ki_type != KnowledgeInteractionType.ANSWER:
            raise ValueError(f"{gp.name}({ki_type}): GraphPattern extension supports only ANSWER interaction")
        sc_ki = gp.init_sc_ki(ki_type=ki_type)
        return self.ki_cache[self.kb_id][sc_ki]

    @property
    def sc_list(self) -> List[SmartClient]:
        # TODO: make a service that holds KE server smartconnectors data (kb_ids with graph patterns),
        #  KE server doesn't keep them while the client is offline (after some time, by default 10 seconds,
        #  information about smart connector client is removed)
        if self._sc_list is None:
            from ke_client import KERestClient
            # todo: cache kb list with timeout
            self._sc_list = KERestClient.get_client().list_sc()
        return self._sc_list

    def match_ask(self, ki_name: str, handler: Optional[Callable]) -> List[KnowledgeInteraction]:
        additional_patterns: List[KnowledgeInteraction] = []
        for i, sc in enumerate(self.sc_list):
            kb_id = sc.knowledge_base_id
            ki_pattern: KIPattern = self.match_kb_ask(ki_name=ki_name, other_kb_id=kb_id)
            if ki_pattern is not None:
                # todo: check if similar graph pattern hasn't been already added to the list
                ki = KnowledgeInteraction(ki_name=f"ext_{i}-{ki_name}", handler=handler,
                                          ki_type=KnowledgeInteractionType.parse(ki_pattern.interaction_type),
                                          graph_pattern=ki_pattern.graph_pattern_new)
                additional_patterns.append(ki)
        return additional_patterns

    def match_kb_ask(self, ki_name: str, other_kb_id: str) \
            -> Optional[KIPattern]:
        from ke_client import ke_settings
        if ke_settings.extend_graph_patterns:
            logging.warning("ke_extend_graph_patterns is disabled ")
            return None
        ki_pattern: KIPattern = self.ki_cache[self.kb_id].ki_patterns[ki_name]
        if other_kb_id not in self.ki_cache:
            from ke_client import KERestClient
            kb_cache = SemanticExt.KBCache(kb_id=other_kb_id, ki_patterns={})
            from ke_client import KERestClient
            for ki in KERestClient.get_client().get_sc_ki(kb_id=other_kb_id):
                if ki.knowledge_interaction_type == KnowledgeInteractionType.ASK:
                    kb_cache.set_item(ki=ki)

            self.ki_cache[other_kb_id] = kb_cache
        other_kb_cache = self.ki_cache[other_kb_id]
        if self._sub_graph_check(ki_pattern=ki_pattern, other_kb_cache=other_kb_cache):
            return None
            # return {}
        # here starts pattern inference /extensions

        if ke_settings.has_extend_graph_patterns_mode(GraphPatternExtMode.TRIPLE_MATCH):
            for other_pattern in other_kb_cache.ki_patterns.values():
                # triple match - no sparql
                # other_pattern = other_kb_cache[other_ki]
                start = time.time()
                try:
                    extended_pattern = self._check_extra_triple(ki_id=other_pattern.ki_id,
                                                                ask_triples=other_pattern.triples,
                                                                ki_pattern=ki_pattern)
                    if extended_pattern is not None:
                        return extended_pattern
                finally:
                    if (time.time() - start) > 0.05:
                        logging.warning(f"Long TRIPLE_MATCH  {time.time() - start}s")
                        # other modes
        if ke_settings.has_extend_graph_patterns_mode(GraphPatternExtMode.SPARQL_MATCH):
            # for other_ki in ki_list:
            for other_pattern in other_kb_cache.ki_patterns.values():
                # other_pattern = other_kb_cache[other_ki]
                start = time.time()
                try:
                    # sparql
                    extended_pattern: Optional[KIPattern] \
                        = self._extend_variables(other_pattern=other_pattern, ki_pattern=ki_pattern)
                    if extended_pattern is not None:
                        return extended_pattern
                finally:
                    if (time.time() - start) > 0.25:
                        logging.warning(f"Long SPARQL_MATCH  {time.time() - start}s")
        if ke_settings.has_extend_graph_patterns_mode(GraphPatternExtMode.ONTOLOGY_SPARQL_MATCH):
            for other_pattern in other_kb_cache.ki_patterns.values():
                # for other_ki in ki_list:
                # other_pattern = other_kb_cache[other_ki]
                # Extend pattern with ontology
                start = time.time_ns()
                try:
                    # ontology inference + sparql
                    extended_pattern: Optional[KIPattern] \
                        = self._infer_triples(other_pattern=other_pattern, ki_pattern=ki_pattern)
                    if extended_pattern is not None:
                        return extended_pattern
                finally:
                    if (time.time() - start) > 0.5:
                        logging.warning(f"Long ONTOLOGY_SPARQL_MATCH  {time.time() - start}s")

        return None

    @staticmethod
    def _check_extra_triple(ki_id: str, ask_triples: List[Tuple], ki_pattern: KIPattern):
        # TODO: find the biggest matching graph or the smallest?
        # similar to previous , but handles the problem with constants in the graph bindings
        # (one graph has variable and the other has predefined URI)
        matches = triple_subgraph_check(ki_pattern.triples, ask_triples)
        if matches:
            # ASK graph pattern has extra triples with variables
            #  answer graph is a  sub graph of ASK, find missing triples and set as rdf nil
            # matches = self.triple_subgraph_check(ask_triples, ki_pattern.triples)
            new_triples, new_triple_map, all_triple_mapping = extract_new_triples(ask_triples, ki_pattern.triples)
            if new_triples is None:
                return None
            ki_pattern.set_new_triples(ki_id=ki_id, new_triples=new_triples, mapping=all_triple_mapping,
                                       new_mapping=new_triple_map)
            return ki_pattern
        return None

    @staticmethod
    def _sub_graph_check(ki_pattern: KIPattern, other_kb_cache: KBCache):

        for other_pattern in other_kb_cache.ki_patterns.values():
            # other_pattern = other_kb_cache[other_ki]
            if triple_subgraph_check(other_pattern.triples, ki_pattern.triples):
                # print(f"TRIPLE SUBGRAPH MATCH: {other_pattern} with {ki_pattern}")
                return True
        for other_pattern in other_kb_cache.ki_patterns.values():
            # other_pattern = other_kb_cache[other_ki]
            if matches_pattern(ki_pattern.processed_pattern, query=other_pattern.sparql_ask):
                # print(f"SPARQL SUBGRAPH MATCH: {other_pattern} with {ki_pattern}")
                return True

    @staticmethod
    def _extend_variables(other_pattern: KIPattern, ki_pattern: KIPattern) -> Optional[KIPattern]:
        """
        subgraph check with sparql
        extend current graph pattern with rdf:nil variables
        :param other_pattern:
        :return:
        """
        matches = matches_pattern(other_pattern.processed_pattern, query=ki_pattern.sparql_ask)
        if matches:
            # Other graph has some extra variables , set them as nil
            new_triples, new_triple_map, all_triple_mapping = extract_new_triples(other_pattern.triples,
                                                                                  ki_pattern.triples)
            # check this before checking triples with RDF nil , find missing triples and add them as RDF nil

            ki_pattern.set_new_triples(ki_id=other_pattern.ki_id, new_triples=new_triples,
                                       mapping=all_triple_mapping, new_mapping=new_triple_map)
            return ki_pattern
        else:
            return None

    @staticmethod
    def _infer_triples(other_pattern: KIPattern, ki_pattern: KIPattern) -> Optional[KIPattern]:
        """
        infer triples using ontology - subgraph check using inferred triples  and sparqkl
        :param other_pattern:
        :param ki_pattern:
        :return:
        """
        matches = matches_pattern(ki_pattern.extended_pattern, query=other_pattern.sparql_ask)
        if matches:
            # extended graph matches, all triples with extra knowledge are allowed
            # ASK graph pattern is subgraph of answer
            # find/infer missing triples (based on ontology, rdf nil is not required here)
            # from ASK and add to answer
            new_triples, new_triple_map, all_triple_mapping = extract_new_triples(other_pattern.triples,
                                                                                  ki_pattern.triples,
                                                                                  allow_extra_knowledge=True)
            ki_pattern.set_new_triples(ki_id=other_pattern.ki_id, new_triples=new_triples,
                                       mapping=all_triple_mapping, new_mapping=new_triple_map)
            return ki_pattern
        else:
            return None
