# CipherCaller example empty plugin
# This plugin does no processing at all. It can serve as a base for your own implementations!
# You can use this file as reference for implementing plugins that suit your needs

from src.plugins.util.template_plugin import Plugin
from src.benchmarking import TimestampLogger
import logging
import socket
import yaml
# Remember to add your imports to src/plugins/util/plugin-requirements.txt

logger = logging.getLogger(__name__)

class Empty(Plugin):  # You can change the class name to reflect what the plugin provides

# === COMMON INITIALIZATION === #  Keep in mind that the sender and receiver have separate Plugin object instances, so variable values are not shared between them
    def __init__(self, config: dict) -> None:
        self.main_plugin_config = config.get("plugin", {})

        # Get this plugin's configuration
        if (config_path := self.main_plugin_config.get("config_path", None)) is not None:
            self.this_plugin_config = yaml.safe_load(open(config_path))
        else:
            raise RuntimeError(
                f"{type(self).__name__} did not find path to own configuration in config.yaml! (config.yaml -> plugin -> config_path)"
            )
        

# === SENDER METHODS === #
    def sender_key_exchange(self, sockfd: socket.socket, logger_object:TimestampLogger=None) -> None:
        return
    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        return chunk
    
    def sender_cleanup(self) -> None:
        return


# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket.socket, logger_object:TimestampLogger=None) -> None:
        return
    
    def receiver_extend_buffer(self, buffer_size: int) -> int:
        return buffer_size

    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        return chunk
    
    def receiver_cleanup(self) -> None:
        return