import inspect
import re
from string import Template
from typing import TypeVar, Generic, Type, Union, Callable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel
from rdflib import URIRef

T = TypeVar('T')

__PARAM_REGEX__ = r"\${([a-zA-Z_][a-zA-Z0-9_]*)}"


def convert(v: str, t: inspect.Parameter):
    if t.annotation in [int, float, str]:
        return t.annotation(v)
    else:
        return v


class UriTemplate(Generic[T]):
    def __init__(self, uri_template: str, t: Type[T],
                 allowed_partial: bool = False, allowed_none: bool = False,
                 allowed_extra: bool = False) -> None:
        self.uri_template = uri_template
        # self.uri_pattern = re.sub(r"\${(\w+)}", r"(?P<\1>[^/]+)", uri_template)
        self.__uri_pattern__ = re.sub(__PARAM_REGEX__, r"(?P<\1>[^/]+)", uri_template)
        self.__uri_keys__ = [*re.compile(self.__uri_pattern__).groupindex]
        self.__obj_attr__ = inspect.signature(t).parameters
        self.__obj_attr_keys__ = inspect.signature(t).parameters.keys()
        for param_key in self.__obj_attr_keys__:
            # if param_key not in self.__uri_keys__:
            if (param_key != 'prefix' and param_key != 'uri' and param_key != 'uri_template' and
                    (not allowed_extra and param_key not in self.__uri_keys__)):
                raise Exception(f"missing argument '{param_key}'  in template: '{uri_template}'")
        if not allowed_partial:
            for param_key in self.__uri_keys__:
                # if param_key not in self.__uri_keys__:
                if not allowed_partial and param_key not in self.__obj_attr_keys__:
                    raise Exception(f"missing argument '{param_key}'  in: '{t}'")
            self.__partial_uri_keys__ = self.__uri_keys__
        else:
            self.__partial_uri_keys__ = {k for k in self.__uri_keys__ if k in self.__obj_attr_keys__}
        self.__uri_obj_class__ = t
        self.__allowed_none__ = allowed_none
        str_template = Template(uri_template)
        self.__uri_builder__: Callable[[dict], str] = lambda d: str_template.safe_substitute(d)

    # def __setattr__(self, name: str, value):
    #     raise Exception('immutable object')

    @property
    def __str__(self):
        return f"UriTemplate parser for: {self.__uri_obj_class__} ({self.uri_template}) "

    def parse(self, uri: [str, URIRef], prefix: str = "") -> T:
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        uri = str(uri)[len(prefix):]
        matched_args = re.match(self.__uri_pattern__, uri)
        kwargs = {k: convert(v, self.__obj_attr__[k])
                  for k, v in matched_args.groupdict().items()
                  if k in self.__obj_attr_keys__}

        if issubclass(self.__uri_obj_class__, SplitURIBase):
            return self.__uri_obj_class__(uri=uri, uri_template=self.uri_template, prefix=prefix, **kwargs)
        else:
            return self.__uri_obj_class__(prefix=prefix, **kwargs)
        # return self.uri_type(**kwargs)

    def build(self, t: T, prefix: str = "") -> str:
        uri_dict = {k: v for k, v in vars(t).items()
                    if k in self.__partial_uri_keys__}
        if not self.__allowed_none__:
            for k, v in uri_dict.items():
                if v is None:
                    raise Exception(
                        f"None value({k})   not allowed in: {self.uri_template} : {self.__uri_obj_class__}")
        for k, v in uri_dict.items():
            if "/" in str(v):
                raise ValueError(
                    f"Separator '/' not allowed for {k}  : {self.uri_template} : {self.__uri_obj_class__}")

        return prefix + self.__uri_builder__(uri_dict)

    def uri_ref(self, t: T, prefix: str = "") -> URIRef:
        return URIRef(self.build(t, prefix=prefix))

    def n3(self, t: T, prefix=""):
        return self.uri_ref(t, prefix=prefix).n3()


U = TypeVar("U", bound="SplitURIBase")


class SplitURIBase(BaseModel):
    __uri_template_parser__: UriTemplate

    __prefix__: str

    # def __init__(self,prefix:Optional[str]=None, **kwargs):
    def __init__(self, prefix: Optional[str] = None, **kwargs):
        # TODO: check if class is decorated
        super().__init__(**kwargs)
        if prefix is None:
            self.__prefix__ = ""
        elif prefix.endswith("/"):
            self.__prefix__ = prefix
        else:
            self.__prefix__ = prefix + "/"
        # setattr(self.__class__, "__uri_template_parser__", UriTemplate(uri_template=uri_template, t=self.__class__))

    def n3(self) -> str:
        """

        :return: string rdf uri  binding (<uri>)
        """
        # TODO: check if class is decorated
        return self.__class__.__uri_template_parser__.n3(self, prefix=self.__prefix__)

    @staticmethod
    def normalize_kb_id(kb_id) -> str:
        if "://" not in kb_id:
            kb_id = "http://" + kb_id
        return urlparse(kb_id).netloc

    @property
    def uri(self) -> str:
        """
        :return: uri value
        """
        # TODO: check if class is decorated
        return self.__class__.__uri_template_parser__.build(self, prefix=self.__prefix__)

    def append(self, suffix: str):
        if not suffix.startswith("/"):
            suffix = "/" + suffix
        uri = self.uri
        if uri.endswith("/"):
            return uri[:-1] + suffix
        else:
            return uri + suffix

    def __str__(self) -> str:
        """
        :return: uri value
        """
        # TODO: check if class is decorated
        return self.__class__.__uri_template_parser__.build(self, prefix=self.__prefix__)

    @property
    def uri_ref(self) -> URIRef:
        """
        :return: RDFUri instance
        """
        # TODO: check if class is decorated
        return self.__class__.__uri_template_parser__.uri_ref(self, prefix=self.__prefix__)

    @classmethod
    def parse(cls: Type[U], uri: [str, URIRef], prefix: str = "") -> U:
        raise NotImplementedError(
            "Class is not decorated with '@ki_split_uri', decorate class or override 'parse' class method ")


def ki_split_uri(uri_template: str):
    """
    URI decorator
    :param uri_template:
    :return:
    """

    # uri_pattern = re.sub(__PARAM_REGEX__, r"(?P<\1>[^/]+)", uri_template)

    def deco(cls: Union[Type, Type[SplitURIBase]]):
        if not issubclass(cls, SplitURIBase):
            # is splituribase type required ?
            raise Exception("Invalid class")
        uri_parser = UriTemplate(uri_template=uri_template, t=cls)
        setattr(cls, "__uri_template_parser__", uri_parser)
        cls.__uri_template_parser__ = uri_parser
        cls.parse = lambda uri, prefix="": uri_parser.parse(uri=uri, prefix=prefix)

        return cls

    return deco

# def ki_split_uri(uri_template: str):
#     uri_pattern = re.sub(__PARAM_REGEX__, r"(?P<\1>[^/]+)", uri_template)
#
#     def deco(cls: Union[Type, Type[SplitURIBase]]):
#         # param_keys = inspect.signature(cls).parameters
#         uri_keys = [*re.compile(uri_pattern).groupindex]
#         params = inspect.signature(cls).parameters
#         for param_key in params.keys():
#             if param_key != 'uri' and param_key != 'uri_template' and param_key not in uri_keys:
#                 raise Exception(f"missing argument '{param_key}'  in template: '{uri_template}'")
#
#         # test class type (subbclass of)
#         # test subclass
#         def init(*args, **kwargs):
#             if "__uri__" in kwargs:
#                 uri = kwargs["__uri__"]
#             elif "uri" in kwargs:
#                 uri = kwargs["uri"]
#             else:
#                 uri = args[0]
#             if type(uri) not in [str, URIRef]:
#                 raise Exception("there is no given valid uri")
#             matched_args = re.match(uri_pattern, uri)
#             class_kwargs = {k: convert(v, params[k])for k,v in matched_args.groupdict().items()if k in params.keys()}
#             if issubclass(cls, SplitURIBase):
#                 return cls(uri=uri, uri_template=uri_template, **class_kwargs)
#
#             return cls(**class_kwargs)
#
#         return init
#
#     return deco
