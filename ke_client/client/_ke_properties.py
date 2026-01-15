from typing import Optional, Dict, Any

from pydantic import Field, Extra
from pydantic_settings import SettingsConfigDict, BaseSettings

import ke_client
from ke_client.ki_model import GraphPattern
from ke_client.utils import load_yml_obj, DictBaseSettings, validate_kb_id
from ke_client.utils.enum_utils import EnumUtils
import ke_client.ke_vars as ke_vars


class KnowledgeInteractionTypeName(EnumUtils):
    POST = "post"
    ASK = "ask"
    REACT = "react"
    ANSWER = "answer"


class KESettings(DictBaseSettings):
    # knowledge_base_id: str = Field(...)
    knowledge_base_id: Optional[str] = None
    rest_endpoint: str = Field(default="http://localhost:8280/rest/")
    ki_config_path: Optional[str] = Field(default=None)
    ki_config_vars_path: Optional[str] = Field(default=None)
    reasoner_level: int = Field(default=1)
    ki_vars: Optional[dict[str, Any]] = Field(default=None)
    model_config = SettingsConfigDict(env_prefix='KE_', env_file=ke_vars.ENV_FILE, env_file_encoding="utf-8",
                                      extra="ignore")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, _env_file=ke_vars.ENV_FILE, **kwargs)
        if self.knowledge_base_id is not None:
            self.knowledge_base_id = validate_kb_id(self.knowledge_base_id)

    def get_ki_vars(self) -> Dict[str, Any]:
        ki_vars: dict
        if self.ki_vars is not None:
            ki_vars = {**self.ki_vars}
        else:
            ki_vars = {}
        if self.knowledge_base_id is None:
            raise Exception("Unknown base id")
        if self.ki_config_vars_path is None:
            return {**ki_vars, **{"KB_ID": self.knowledge_base_id}}
        else:
            yml_conf = load_yml_obj(self.ki_config_vars_path, section="KI_VARS".lower())
            #         TODO: flatten dict?
            yml_conf = {k.upper(): v for k, v in yml_conf.items() if
                        type(v) is str or type(v) is int or type(v) is float}
            yml_conf["KB_ID"] = self.knowledge_base_id
            return {**ki_vars, **{yml_conf}}

    @classmethod
    def load(cls, yml_path: Optional[str] = None, **kwargs):
        # regex = re.compile(r'^__?.+_?_?$')
        if yml_path:
            app_config = load_yml_obj(yml_path, section="KE".lower(), settings_constructor=dict)
            keys = [k for k in vars(cls)["__pydantic_fields__"].keys()]

            fields = {k: f for k, f in app_config.items() if k in keys}
            return cls(dict_settings=fields)

        return cls(dict_settings={})
        # return super().load(yml_path=yml_path, section_name="KE".lower())


class KnowledgeInteractionConfig(BaseSettings, extra=Extra.allow):
    __SECTION__ = "knowledge_engine"
    kb_name: str = Field(...)
    # knowledge_base_id: str = Field(...)
    kb_description: str = Field(...)
    # deprecated?
    # ki_graph_patterns: Optional[GraphPatterns] = None
    graph_patterns: Optional[Dict[str, GraphPattern]] = None
    prefixes: Optional[dict] = None

    # include: Optional[]

    def graph_patterns_safe(self) -> Dict[str, GraphPattern]:
        return self.graph_patterns if self.graph_patterns is not None else {}

    def prefixes_safe(self) -> Dict:
        return self.prefixes if self.prefixes is not None else {}

    # @classmethod
    # def settings_customise_sources(cls, settings_cls, **kwargs):
    #     return (YamlConfigSettingsSource(settings_cls),)


ke_settings = KESettings()
ki_conf: Optional[KnowledgeInteractionConfig] = None


def configure_ke_client(yml_config_path: str):
    global ke_settings
    ke_settings = KESettings.load(yml_path=yml_config_path)

    configure_ki()


def configure_ki():
    global ki_conf
    global ke_settings
    ki_conf_file = ke_settings.ki_config_path if ke_settings.ki_config_path is not None else ke_vars.KI_CONFIG_PATH
    import os

    if not os.path.exists(ki_conf_file):
        raise FileNotFoundError(
            f"KI config file: '{ki_conf_file}' does not exist." +
            " Set ke_client.KI_CONFIG_PATH or KI_CONFIG_PATH env variable ")

    _ki_conf = load_yml_obj(ki_conf_file, section=KnowledgeInteractionConfig.__SECTION__, settings_constructor=dict,
                            file_vars=ke_settings.get_ki_vars())
    ki_conf = KnowledgeInteractionConfig.model_validate(_ki_conf)
    if "include" in _ki_conf:
        graph_patterns: Dict[str, GraphPattern] = {}
        prefixes = {}

        # ki_vars
        def include(include_file_path: str):
            included_yml = load_yml_obj(include_file_path, section=KnowledgeInteractionConfig.__SECTION__,
                                        settings_constructor=dict, file_vars=ke_settings.get_ki_vars())
            included_conf = KnowledgeInteractionConfig.model_validate(included_yml)
            for k in included_conf.graph_patterns_safe().keys():
                if k in graph_patterns.keys():
                    raise Exception(f"Duplicate graph pattern key: '{k}'.")
            graph_patterns.update(included_conf.graph_patterns_safe())
            prefixes.update(included_conf.prefixes_safe())

        if type(_ki_conf["include"]) is list:
            for include_file in _ki_conf["include"]:
                include(include_file)
                # included_yml = load_yml_obj(include_file, section=KnowledgeInteractionConfig.__SECTION__,
                #                             settings_constructor=dict, file_vars=ke_settings.get_ki_vars())
                # included_conf = KnowledgeInteractionConfig.model_validate(included_yml)
                # graph_patterns.update(included_conf.graph_patterns_safe())
                # prefixes.update(included_conf.prefixes_safe())
        else:
            include(_ki_conf["include"])
            # included_yml = load_yml_obj(_ki_conf["include"], section=KnowledgeInteractionConfig.__SECTION__,
            #                             settings_constructor=dict, file_vars=ke_settings.get_ki_vars())
            # included_conf = KnowledgeInteractionConfig.model_validate(included_yml)
            # graph_patterns.update(included_conf.graph_patterns_safe())
            # prefixes.update(included_conf.prefixes_safe())
        if len(prefixes) > 0:
            prefixes.update(ki_conf.prefixes_safe())
            ki_conf.prefixes = prefixes
        if len(graph_patterns) > 0:
            graph_patterns.update(ki_conf.graph_patterns_safe())
            ki_conf.graph_patterns = graph_patterns

    return ki_conf
