# CipherCaller template plugin
# 
# This file represents a template CipherCaller plugin, outlining the necessary functions and their purpose.
# For ease of use, functions are arranged separately for the sender and receiver.
#
# === IMPORTANT! === #
# When implementing your own plugin, please define
# a class that inherits from Plugin defined below!


from abc import ABC
import logging

logger = logging.getLogger(__name__)

class Plugin(ABC):

# === COMMON INITIALIZATION === #
    def __init__(self, config: dict) -> None:
        self.plugin_config = config.get("plugin", {})
        # You can also load other configuration keys here


# === SENDER METHODS === #
    def sender_key_exchange(self) -> None:
        # This function is called during sender initialization.
        #
        # Note: If you don't want a key exchange in your plugin,
        # please define this as an empty function.
        raise NotImplementedError(
            f"{type(self).__name__} does not implement sender_key_exchange()"
        )
    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        # This function is called for each data chunk read by the sender before transmission.
        # The output of this function is trasmitted as-is right after returning.
        # 
        # Note: If you don't want encryption in your plugin,
        # please define this function to return the chunk as-is.
        raise NotImplementedError(
            f"{type(self).__name__} does not implement sender_encrypt_chunk()"
        )
    
    def sender_cleanup(self) -> None:
        # This function is called right before SENDER program exit. Use it to close descriptors, etc.
        pass


# === RECEIVER METHODS === #
    def receiver_key_exchange(self) -> None:
        # This function is called during receiver initialization.
        #
        # Note: If you don't want a key exchange in your plugin,
        # please define this as an empty function.
        raise NotImplementedError(
            f"{type(self).__name__} does not implement sender_key_exchange()"
        )
    
    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        # This function is called for each data chunk received by the receiver.
        # The output of this function is written to the specified file or played back as-is
        # right after returning.
        # 
        # Note: If you don't want encryption in your plugin,
        # please define this function to return the chunk as-is.
        raise NotImplementedError(
            f"{type(self).__name__} does not implement sender_encrypt_chunk()"
        )
    
    def receiver_cleanup(self) -> None:
        # This function is called right before RECEIVER program exit. Use it to close descriptors, etc.
        pass