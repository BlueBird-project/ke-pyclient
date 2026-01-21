from typing import Dict, Optional

from .utils import load_yml_obj
from .client import ki_object, SplitURIBase, ki_split_uri, rdf_nil, is_nil, BindingsBase, KITypeError, KIError, \
    KESettings, KnowledgeInteractionConfig, KEClient

ke_settings = KESettings()
ki_conf: Optional[KnowledgeInteractionConfig] = None


def configure_ke_client(yml_config_path: str):
    """
    load KE settings
    :param yml_config_path:
    :return:
    """
    global ke_settings
    ke_settings = KESettings.load(yml_path=yml_config_path)

    configure_ki()


def configure_ki():
    """
    load knowledge interactions
    :return:
    """
    # global KI_CONFIG_PATH
    import ke_client.ke_vars as ke_vars
    global ki_conf
    global ke_settings

    ki_conf_file = ke_settings.ki_config_path if ke_settings.ki_config_path is not None else ke_vars.KI_CONFIG_PATH
    import os

    if not os.path.exists(ki_conf_file):
        raise FileNotFoundError(
            f"KI config file: '{ki_conf_file}' does not exist. " +
            "Set ke_client.KI_CONFIG_PATH or KI_CONFIG_PATH env variable ")

    _ki_conf = load_yml_obj(ki_conf_file, section=KnowledgeInteractionConfig.__SECTION__, settings_constructor=dict,
                            file_vars=ke_settings.get_ki_vars())
    ki_conf = KnowledgeInteractionConfig.model_validate(_ki_conf)
    if "include" in _ki_conf:
        from ke_client.ki_model import GraphPattern
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
