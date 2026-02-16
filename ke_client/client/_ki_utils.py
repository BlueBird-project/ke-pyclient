import inspect
import logging
import sys
from types import ModuleType
from typing import Dict, Any, List, Optional, get_origin, get_args, Union

from ke_client.utils.enum_utils import EnumItem
from pydantic import BaseModel

from ke_client.ki_model import rdf_binding_pattern, KnowledgeInteractionType, KnowledgeInteraction

from ._ki_bindings import BindingsBase, TargetedBindings

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


# def init_ki_graph_pattern(gp_name, ki_name: str) -> GraphPattern:
#     gp = require_graph_pattern(gp_name=gp_name)
#     return gp.model_copy(update={"name": f"{ki_name}-{gp.name}"})


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


# def _init_ki_kwargs(wrapper_args, params: Dict[str, inspect.Parameter]):
#     _kwargs = {k: v for k, v in {"ki_id": wrapper_args[0], "bindings": wrapper_args[1]}.items() if
#                k in params}
#     bindings_annotation = get_origin(params["bindings"].annotation)
#     if "bindings" in _kwargs and (bindings_annotation is not None) and issubclass(bindings_annotation, list):
#         # if "bindings" in _kwargs and issubclass(params["bindings"].annotation, BindingsBase):
#         cls_annotations = get_args(params["bindings"].annotation)
#         if len(cls_annotations) == 1 and issubclass(cls_annotations[0], BindingsBase):
#             _kwargs["bindings"] = [cls_annotations[0](**b) for b in _kwargs["bindings"]]
#     return _kwargs


def _verify_object_ki(gp_name: str, bindings_arg_annotation, call_ctx: str):
    """
    check if KI name for bindings argument object match the KI handler
    :param gp_name:
    :param bindings_arg_annotation:
    :param call_ctx:
    :return: True if interaction is wrapped with object
    """
    try:
        generic_annotation: Any = get_origin(bindings_arg_annotation)
        if generic_annotation is not None and issubclass(generic_annotation, list):
            cls_annotations = get_args(bindings_arg_annotation)
            if (len(cls_annotations) == 1 and (not type(cls_annotations[0]) is dict)
                    and issubclass(cls_annotations[0], BindingsBase)):
                if not hasattr(cls_annotations[0], "__gp_name__"):
                    logging.warning(f"Object type not decorated  {call_ctx}.  ")
                else:
                    if gp_name != cls_annotations[0].__gp_name__:
                        raise KIError(f"Different graph patterns for function ({gp_name}) and" +
                                      f"object type ({cls_annotations[0].__name__}:{cls_annotations[0].__gp_name__})",
                                      ctx=call_ctx)
                    else:
                        return
            else:
                logging.warning(
                    f"Missing List's type annotation for `bindings` in {call_ctx}. Expected: `List[BindingsBase]`" +
                    f", got: `{str(bindings_arg_annotation)}` .")
        else:
            if bindings_arg_annotation is not None and bindings_arg_annotation is not inspect.Signature.empty:
                raise KIError(f"Expected empty type or List[BindingsBase]," +
                              f" received: ({bindings_arg_annotation.__name__} )",
                              ctx=call_ctx)
                # else: empty type proceed
    except TypeError:
        raise KIError(f"Invalid bindings object type Expected empty type or List[BindingsBase]," +
                      f" received: ({bindings_arg_annotation.__name__} )",
                      ctx=call_ctx)


def verify_in_bindings_ki(gp_name: str, params: Dict[str, inspect.Parameter], call_ctx: str):
    """
    check if KI name for input bindings argument object match the KI handler
    :param gp_name:
    :param params:
    :param call_ctx:
    :return:
    """
    if "bindings" in params:
        bindings_annotation = params["bindings"].annotation
        return _verify_object_ki(gp_name=gp_name, bindings_arg_annotation=bindings_annotation, call_ctx=call_ctx)
    else:
        logging.warning(f"Missing function's `bindings` arg in {call_ctx}")


def verify_out_bindings_ki(gp_name: str, bindings_annotation, call_ctx: str):
    """

    check if KI name for returned bindings argument object match the KI handler
    :param gp_name:
    :param bindings_annotation:
    :param call_ctx:
    :return:
    """
    if type(bindings_annotation) is TargetedBindings:
        _verify_object_ki(gp_name=gp_name, bindings_arg_annotation=bindings_annotation.__annotations__["bindings"],
                          call_ctx=call_ctx)
    else:
        _verify_object_ki(gp_name=gp_name, bindings_arg_annotation=bindings_annotation, call_ctx=call_ctx)


def _serialize_returned_bindings(bindings: Union[TargetedBindings, List[BindingsBase], List[Dict], None],
                                 ki_type: EnumItem) -> \
        Union[Dict, List[Dict[str, str]]]:
    if bindings is None:
        bindings = []
    if type(bindings) is TargetedBindings:
        # bindings: TargetedBindings
        return bindings.json(ki_type=ki_type)
    if type(bindings) is not list:
        bindings = [bindings]
    if len(bindings) == 0:
        return bindings
    # if issubclass(type(bindings ), TargetedBindings)  :
    if issubclass(type(bindings[0]), BindingsBase):
        b: BindingsBase
        bindings = [b.serialize(ki_type=ki_type) for b in bindings]
    return bindings


def prepare_ke_request(bindings: Union[TargetedBindings, List[BindingsBase], List[Dict], None],
                       ki: KnowledgeInteraction, call_ctx):
    logging.debug(f"{ki.ki_type} bindings: {ki.graph_pattern.name} = {bindings}")
    ki_bindings = _serialize_returned_bindings(bindings=bindings, ki_type=ki.ki_type)

    if type(bindings) is TargetedBindings:
        _verify_pattern_bindings(name=ki.graph_pattern.name, ki_type=ki.ki_type, ki_bindings=ki_bindings["bindingSet"],
                                 call_ctx=call_ctx)

    else:
        _verify_pattern_bindings(name=ki.graph_pattern.name, ki_type=ki.ki_type, ki_bindings=ki_bindings,
                                 call_ctx=call_ctx)
    return ki_bindings


def _verify_pattern_bindings(name: str, ki_type: EnumItem, ki_bindings: Optional[List[Dict]] = None,
                             call_ctx: Optional[str] = None):
    """
    verify pattern bindings before sending to the
    :param name:
    :param ki_type:
    :param ki_bindings:
    :param call_ctx:
    :return:
    """
    if call_ctx is None:
        raise ValueError("None call_ctx not supported")
    gp: GraphPattern = require_graph_pattern(gp_name=name)
    if ki_bindings is None:
        # todo log warning ?
        ki_bindings = []
    if ki_type == KnowledgeInteractionType.ASK:
        _verify_required_bindings(gp=gp, ki_bindings=ki_bindings, call_ctx=call_ctx)
    elif len(ki_bindings) > 0:
        if ki_type == KnowledgeInteractionType.REACT:
            if gp.result_pattern_value is None:
                gp_vars = {}
            else:
                gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.result_pattern_value)}
        else:
            gp_vars = {k[1:] for k in rdf_binding_pattern.findall(gp.pattern_value)}
        for ki_binding in ki_bindings:
            args_missing = [ki_arg for ki_arg in ki_binding.keys() if ki_arg not in gp_vars]
            if len(args_missing) > 0:
                raise KIError(
                    f" KI {ki_type}:{name} is missing variables: "
                    f"{",".join([f"'{v}'" for v in args_missing])} ", ctx=call_ctx)


def _verify_required_bindings(gp: GraphPattern, ki_bindings: Optional[List[Dict]] = None,
                              call_ctx: Optional[str] = None):
    """
    :param call_ctx:
    :param gp:
    :param ki_bindings:
    :return:
    """
    for ki_binding in ki_bindings:
        try:
            gp.verify_required_bindings(bindings=ki_binding)
        except KeyError as err:
            raise KIError(f"Invalid ki bindings: {err}", ctx=call_ctx) from err


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
        cls.__gp_name__ = name
        return cls

    return deco


def default_handler(ki_id: str, bindings: Optional[Dict[str, Any]]):
    logging.warning(f"No handler for {ki_id}.")
    logging.debug(f"Bindings arrived for {ki_id}: {bindings}")
    return []


class _KIUtilsModule(ModuleType):

    def __init__(self, name, **kwargs):
        super().__init__(name)
        self.__dict__.update(kwargs)

    def __setattr__(self, name, value):
        raise AttributeError(f"Trying to modify read-only property {name}")


sys.modules[__name__] = _KIUtilsModule(__name__, **globals())
