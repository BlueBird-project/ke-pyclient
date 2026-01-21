from typing import Callable, Optional, Union, Dict
from urllib.parse import urlparse

import yaml
from pydantic import PrivateAttr

from pydantic_settings import BaseSettings, InitSettingsSource, PydanticBaseSettingsSource, SettingsConfigDict


class MergeConfigMixin:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        merged = {}
        for base in reversed(cls.__mro__[1:]):  # walk bases
            if hasattr(base, "model_config"):
                merged.update(base.model_config)

        if hasattr(cls, "model_config"):
            merged.update(cls.model_config)

        cls.model_config = SettingsConfigDict(**merged)


class DictBaseSettings(MergeConfigMixin, BaseSettings):
    # dict_settings_: Optional[dict] = Field(..., alias="dict_settings")
    _dict_settings_: Optional[dict] = PrivateAttr(default=None)
    model_config = SettingsConfigDict(populate_by_name=True)

    @classmethod
    def settings_customise_sources(cls,
                                   settings_cls: type[BaseSettings],
                                   init_settings: InitSettingsSource,  # type: ignore[override]
                                   env_settings: PydanticBaseSettingsSource,
                                   dotenv_settings: PydanticBaseSettingsSource,
                                   file_secret_settings: PydanticBaseSettingsSource, ):
        # init_settings.init_kwargs["_dict_settings"] = init_settings.init_kwargs["dict_settings"]
        # init_settings.init_kwargs["_dict_settings_"] = init_settings.init_kwargs["dict_settings"]
        if "dict_settings" in init_settings.init_kwargs:
            cls._dict_settings_ = init_settings.init_kwargs["dict_settings"]

            del init_settings.init_kwargs["dict_settings"]
        else:
            cls._dict_settings_ = {}

        def dict_source(**kwargs):
            return cls._dict_settings_

        # https://docs.pydantic.dev/latest/concepts/pydantic_settings/#customise-settings-sources
        # The order of the returned callables decides the priority of inputs; first item is the highest priority
        return (
            env_settings,  # highest priority , default .env and loaded environemnt var
            dict_source,  # custom settings
            dotenv_settings,  # custom .env file
            init_settings,  # __init__ args
        )

        # return (
        #     init_settings, env_settings,
        #     dict_source,
        # )

    @classmethod
    def load(cls, yml_path: Optional[str] = None, section_name: Optional[str] = None):
        # regex = re.compile(r'^__?.+_?_?$')
        if yml_path:
            app_config = load_yml_obj(yml_path, section=section_name, settings_constructor=dict)
            keys = [k for k in vars(cls)["__pydantic_fields__"].keys()]
            fields = {k: f for k, f in app_config.items() if k in keys}
            return cls(dict_settings=fields)
        return cls(dict_settings={})


def load_yml_obj(config_path: str, section: Optional[str] = None,
                 settings_constructor: Optional[Union[Callable, dict]] = None,
                 file_vars: Optional[Dict] = None) -> Union[dict, object]:
    class YAML:
        def __init__(self, **entries):
            self.__dict__.update(entries)

    try:
        _config = _load_yml(config_path, section, file_vars=file_vars)
        if settings_constructor is not None:
            if settings_constructor is dict:
                if type(_config) is not dict:
                    raise TypeError(f"Expected configuration type: 'dict', actual type: {type(_config)}  ")
                return _config
            return settings_constructor(**_config)
        else:
            return YAML(**_config)
    except FileNotFoundError as error:
        message = "Error: yml config file not found."
        raise FileNotFoundError(error, message) from error


def _load_yml(config_path, section, file_vars: Optional[Dict] = None):
    with open(config_path) as stream:
        try:
            if file_vars:
                from string import Template
                template = Template(stream.read())
                rendered = template.substitute(file_vars)
                _config = yaml.safe_load(rendered, )
            else:
                _config = yaml.safe_load(stream, )
            if section is not None:
                try:
                    _config = _config[section]
                except KeyError:
                    #   Todo: handle  error
                    raise Exception(f"invalid setting section {section}")
        except yaml.YAMLError as exc:
            # TODO: log/handle error
            print(exc)
        # except FileNotFoundError as exc:
        #     # TODO: log/handle error
        #     print(exc)
    return _config


def validate_kb_id(uri: str) -> str:
    if uri is None:
        raise KeyError("knowledge_base_id field of KESettings is None")
    result = urlparse(uri)
    if result.scheme not in ["http", "https"]:
        raise ValueError(f"Invalid uri scheme {result.scheme} in {uri}")
    if result.path.endswith("/"):
        return result.scheme + "://" + result.netloc + result.path[:-1]
    return result.scheme + "://" + result.netloc + result.path
