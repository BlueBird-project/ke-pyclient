from typing import Optional

from ._semantic_utils import KIPattern, SemanticGPExt, is_uri_default

_gp_extender: Optional[SemanticGPExt] = None


def get_gp_extender() -> SemanticGPExt:
    """
    get graph pattern extender
    :return:
    """
    global _gp_extender
    if _gp_extender is None:
        from ke_client import ke_settings
        _gp_extender = SemanticGPExt(kb_id=ke_settings.knowledge_base_id)
    return _gp_extender
