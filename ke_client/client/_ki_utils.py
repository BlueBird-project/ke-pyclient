import logging
import sys
from types import ModuleType
from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel

from ke_client.ki_model import rdf_binding_pattern

from ._ki_bindings import BindingsBase

from ke_client.ki_model import GraphPattern
from ._ki_exceptions import KIError


# TODO make register, and other methods thread safe  -> locks
def assert_bindings_type(bindings: Optional[Any]):
    if bindings is None:
        raise TypeError("Bindings cannot be None")
    if type(bindings) is not list:
        raise TypeError(f"Bindings should be a list not {type(bindings)}")
    # if len(bindings>0):
    #     todo: check all elements


def init_ki_graph_pattern(gp_name, ki_name: str) -> GraphPattern:
    gp = require_graph_pattern(gp_name=gp_name)
    return gp.model_copy(update={"name": f"{ki_name}-{gp.name}"})


def require_graph_pattern(gp_name) -> GraphPattern:
    from ke_client import ki_conf
    if ki_conf is None:
        from ke_client import configure_ki
        logging.info("Configuring KI settings")
        ki_conf = configure_ki()

    if gp_name not in ki_conf.graph_patterns:
        raise Exception(f"{gp_name} graph pattern is not defined")

    gp: GraphPattern = ki_conf.graph_patterns[gp_name]
    return gp


def verify_binding_args(name: str, ki_binding_args: Optional[List[str]] = None, call_ctx: Optional[str] = None,
                        response_class: Optional[Type[BindingsBase]] = None):
    if call_ctx is None:
        raise ValueError("None call_ctx not supported")
    gp: GraphPattern = require_graph_pattern(gp_name=name)
    if ki_binding_args is not None and len(ki_binding_args) > 0:
        gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.pattern_value)}
        args_missing = [ki_arg for ki_arg in ki_binding_args if ki_arg not in gp_vars]
        if len(args_missing) > 0:
            raise KIError(f"Inconsistent args for graph '{name}':"
                          f" {",".join([f"'{arg}'" for arg in args_missing])}", ctx=call_ctx)
    if gp.result_pattern_value is not None and response_class is not None:

        result_gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.result_pattern_value)}
        resp_args_missing = [ki_arg for ki_arg in response_class.binding_keys() if ki_arg not in result_gp_vars]
        if len(resp_args_missing) > 0:
            # TODO: allow extra fields ?
            raise KIError(f"Type: {response_class.__name__} - inconsistent response args for graph {name}:"
                          f" {",".join([f"'{arg}'" for arg in resp_args_missing])}", ctx=call_ctx)
        pattern_args_missing = [pattern_arg for pattern_arg in result_gp_vars if
                                pattern_arg not in response_class.binding_keys()]
        if len(pattern_args_missing) > 0:
            raise KIError(f"Type: {response_class.__name__} - missing pattern's bindings response args for {name}:"
                          f" {",".join([f"'{arg}'" for arg in resp_args_missing])}", ctx=call_ctx)


def syntax_bindings_verification(name: str, ki_bindings: Optional[List[Dict]] = None, call_ctx: Optional[str] = None):
    """
    check if input bindings are in the graph pattern
    :param call_ctx:
    :param name:
    :param ki_bindings:
    :return:
    """
    # TODO: does KE expect always bindings ? can bindings list be none or empty
    if call_ctx is None:
        raise ValueError("None call_ctx not supported")
    gp: GraphPattern = require_graph_pattern(gp_name=name)
    gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.pattern_value)}
    for idx, ki_binding in enumerate(ki_bindings):
        args_missing = [ki_arg for ki_arg in ki_binding.keys() if ki_arg not in gp_vars]
        if len(args_missing) > 0:
            raise KIError(f"Inconsistent args for graph {name}, bindings[{idx}]="
                          f" {",".join([f"'{arg}'" for arg in args_missing])}", ctx=call_ctx)


def verify_required_bindings(name: str, ki_bindings: Optional[List[Dict]] = None, call_ctx: Optional[str] = None):
    """ verify required:  ASK,ANSWER - check if required graph patterns are included in the binding set.
            POST,REACT  require always binding args included
    :param call_ctx:
    :param name:
    :param ki_bindings:
    :return:
    """
    # TODO: does KE expect always bindings ? can bindings list be none or empty
    gp: GraphPattern = require_graph_pattern(gp_name=name)
    if ki_bindings is None or len(ki_bindings) == 0:
        ki_bindings = [{}]
    for ki_binding in ki_bindings:
        try:
            gp.verify_bindings(bindings=ki_binding)
        except KeyError as err:
            raise KIError(f"Invalid ki bindings: {err}" , ctx=call_ctx) from err


def ki_object(name: str, allow_partial: bool = False, result: bool = False):
    """
    ki_object class decorator
    :param name: knowledge interaction name.
    Name used in the config file, without KnowledgeInteractionTypeName prefix which is added on registration
    :param allow_partial: don't check if all graph binding variable are included in the object
    :param result: TRUE if KI object reflects result_pattern (instead of normal graph pattern)
    :return:
    """
    gp: GraphPattern = require_graph_pattern(gp_name=name)
    if not result:
        gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.pattern_value)}
    else:
        gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.result_pattern_value)}

    def deco(cls):
        if issubclass(cls, BaseModel):
            fields = cls.model_fields
        else:
            annotated_fields = vars(cls)["__annotations__"] if "__annotations__" in vars(cls) else []
            other_fields = [k for k, v in vars(cls).items() if not callable(v) and not k.startswith("__")]
            fields = {*other_fields, *annotated_fields}
        if not allow_partial:
            variables_missing = [gp_var for gp_var in gp_vars if gp_var not in fields]
            if len(variables_missing) > 0:
                raise KeyError(
                    f"Class {cls.__module__}.{cls.__name__} is missing variables: "
                    f"{",".join([f"'{v}'" for v in variables_missing])} from graph {name}")
        else:
            variables_missing = [gp_var for gp_var in fields if gp_var not in gp_vars]
            if len(variables_missing) > 0:
                raise KeyError(
                    f"Graph: {name} is missing variables: "
                    f"{",".join([f"'{v}'" for v in variables_missing])} from class {cls.__module__}.{cls.__name__}")
        return cls

    return deco


def default_handler(ki_id: str, bindings: Optional[Dict[str, Any]]):
    logging.warning(f"No handler for {ki_id}.")
    logging.debug(f"Bindings arrived for {ki_id}: {bindings}")
    return [{}]


class _KIUtilsModule(ModuleType):

    def __init__(self, name, **kwargs):
        super().__init__(name)
        self.__dict__.update(kwargs)

    def __setattr__(self, name, value):
        raise AttributeError(f"Trying to modify read-only property {name}")


sys.modules[__name__] = _KIUtilsModule(__name__, **globals())
