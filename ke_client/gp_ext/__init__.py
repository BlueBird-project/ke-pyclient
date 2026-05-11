from ._semantic_utils import KIPattern, SemanticExt

_gp_extender: SemanticExt = None


def get_gp_extender() -> SemanticExt:
    global _gp_extender
    if _gp_extender is None:
        from ke_client import ke_settings
        _gp_extender = SemanticExt(kb_id=ke_settings.knowledge_base_id)
    return _gp_extender
