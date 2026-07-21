# CipherCaller plugin loader
#
# You don't need to modify this file when creating a custom plugin.
# Please follow the plugin convention outlined in src/plugins/template_plugin.py

from .template_plugin import Plugin
import logging
import importlib

logger = logging.getLogger(__name__)

# The following function is entered assuming use_plugin key is set to 'yes'
def load_plugin(config: dict) -> Plugin | None:
    # Get 'name' key value from config.yaml -> plugin
    name = config.get("plugin", {}).get("name", None)

    # Notify user if 'name' not present and return None
    if not name:
        logger.info("Plugin name not supplied in configuration! (config.yaml -> plugin -> name)")  # TODO: Stop here or proceed without plugin?
        return None
    
    # Delete '.py' ending from 'name' just in case
    if len(name > 3) and name[-3:-1] == ".py":
        name = name[:-3]
    
    # Try importing module specified in config
    module_path = f"src.plugins.{name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        raise ImportError(
            f"Plugin '{name}' not found. Tried loading from path: {module_path}. Please ensure the specified plugin is located in the src/plugins/ directory!"
        )

    # Get Plugin subclass from module
    for attribute_name in dir(module):
        cls = getattr(module, attribute_name)

        # Select a class inheriting from Plugin and return an object of that class
        if (isinstance(cls, type)
            and issubclass(cls, Plugin)
            and cls is not Plugin
        ):
            logger.info(f"Loaded plugin {cls.__name__} ({module_path})")
            return cls(config)

    # If no Plugin subclass is found:
    raise RuntimeError(
        f"No Plugin subclass found in {module_path}. Please define a class that inherits from Plugin! (see: src/plugins/template_plugin.py)"
    ) 