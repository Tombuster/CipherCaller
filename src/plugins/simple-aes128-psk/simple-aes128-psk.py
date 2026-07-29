# CipherCaller example AES plugin
#
# You can use this file as reference for implementing plugins that suit your needs

from src.plugins.template_plugin import Plugin
import logging
import socket
import yaml
from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

class SimpleAes128Psk(Plugin):

# === COMMON INITIALIZATION === #
    def __init__(self, config: dict) -> None:
        self.main_plugin_config = config.get("plugin", {})

        # Get this plugin's configuration
        if config_path := self.main_plugin_config.get("config_path", None) is not None:
            self.this_plugin_config = yaml.safe_load(open(config_path))
        else:
            raise RuntimeError(
                f"{type(self).__name__} did not find path to own configuration in config.yaml! (config.yaml -> plugin -> config_path)"
            )

        # Load key from config
        self.key = self.this_plugin_config.get("key", None)
        if self.key is None:
            raise RuntimeError(
                f"{type(self).__name__} did not find key in own configuration! (plugin-config.yaml -> key)"
            )

        # Check key length
        self.key = self.key.encode('utf-8')
        if len(self.key) != 16:
            raise RuntimeError(
                f"{type(self).__name__} invalid length key provided! Must be 16 bytes, got {len(self.key)}. (plugin-config.yaml -> key)"
            )

        # Set up pycryptodome AES
        self.cipher = AES.new(self.key, AES.MODE_CTR)

# === SENDER METHODS === #
    def sender_key_exchange(self, sockfd: socket) -> None:
        return
    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        return self.cipher.encrypt(chunk)
    
    def sender_cleanup(self) -> None:
        return


# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket) -> None:
        return
    
    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        return self.cipher.decrypt(chunk)
    
    def receiver_cleanup(self) -> None:
        return