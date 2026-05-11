from ._gp_validator import GraphValidator
from ._simple_validator import SimpleValidator

_gp_validator: GraphValidator


def get_validator() -> GraphValidator:
    global _gp_validator
    if _gp_validator is None:
        _gp_validator = SimpleValidator.load()
        # _gp_validator = SimpleValidator.load(turtle_files=[
        #     "ontologies/geo.ttl", "ontologies/saref.core.ttl", "ontologies/saref4city.ttl",
        #     "ontologies/saref4ener.ttl", "ontologies/bluebird.ttl", "ontologies/time.ttl"
        # ])
    return _gp_validator
