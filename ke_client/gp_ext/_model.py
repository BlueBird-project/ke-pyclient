from ke_client.utils.enum_utils import EnumItem, BaseEnum


class GraphPatternExtMode(BaseEnum):
    NONE = EnumItem(0b0000)
    TRIPLE_MATCH = EnumItem(0b0001)
    SPARQL_MATCH = EnumItem(0b0010)
    ONTOLOGY_SPARQL_MATCH = EnumItem(0b0100)
