# CipherCaller example AES plugin
#
# You can use this file as reference for implementing plugins that suit your needs

from src.plugins.util.template_plugin import Plugin
import logging
import socket
import yaml
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)

class SimpleAesPsk(Plugin):

# === COMMON INITIALIZATION === #
    def __init__(self, config: dict) -> None:
        self.main_plugin_config = config.get("plugin", {})

        # Get this plugin's configuration
        if (config_path := self.main_plugin_config.get("config_path", None)) is not None:
            self.this_plugin_config = yaml.safe_load(open(config_path))
        else:
            raise RuntimeError(
                f"{type(self).__name__} did not find path to own configuration in config.yaml! (config.yaml -> plugin -> config_path)"
            )

        # Load password from config
        self.password = self.this_plugin_config.get("password", None)
        if self.password is None:
            raise RuntimeError(
                f"{type(self).__name__} did not find password in own configuration! ({config_path} -> password)"
            )

        
        # Load desired key length from config
        self.key_length = self.this_plugin_config.get("key_length", None)
        if self.key_length is None:
            raise RuntimeError(
                f"{type(self).__name__} did not find key length in own configuration! ({config_path} -> key_length)"
            )

        # Check key length
        if self.key_length not in AES.key_size:
            raise RuntimeError(
                f"{type(self).__name__} invalid key length provided! Must be [16, 24, 32] bytes, got {self.key_length}. ({config_path} -> key_length)"
            )

        # Load salt from config
        self.salt = self.this_plugin_config.get("salt", None)
        if self.salt is None:
            raise RuntimeError(
                f"{type(self).__name__} did not find salt in own configuration! ({config_path} -> salt)"
            )

        # Derive key from password
        self.key = PBKDF2(self.password, self.salt, dkLen=self.key_length, count=1000000)

        logger.info("+--- AES info ---")
        logger.info(f"| Key: {self.key}")
        logger.info(f"| Salt: {self.salt}")
        logger.info("+----------------")
        

# === SENDER METHODS === #
    def sender_key_exchange(self, sockfd: socket.socket) -> None:
        return
    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        cipher = AES.new(self.key, AES.MODE_CBC)    # initiate new cipher,
        # logger.info(f"Sender: chunk length: {len(chunk)}")
        if len(chunk) % AES.block_size != 0:
            chunk = pad(chunk, AES.block_size)          # pad,
        # logger.info(f"Sender: chunk head:   {chunk[:10]}")
        # logger.info(f"Sender: chunk tail:   {chunk[-10:]}")
        # logger.info(f"Sender: padded chunk length: {len(chunk)}")
        chunk = cipher.encrypt(chunk)               # encrypt,
        # logger.info(f"Sender: encrypted chunk length: {len(chunk)}")
        chunk = cipher.iv + chunk                   # stick iv at the front
        # logger.info(f"Sender: chunk length with IV: {len(chunk)}")
        # logger.info(f"Sender: sending chunk with IV: {cipher.iv}")
        return chunk
    
    def sender_cleanup(self) -> None:
        return


# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket.socket) -> None:
        return
    
    def receiver_extend_buffer(self, buffer_size: int) -> int:
        # Adjust for padding
        # logger.info(f"Receiver: expanding buffer from length {buffer_size}...")
        if buffer_size % AES.block_size != 0:
            buffer_size += (buffer_size % AES.block_size)
            # logger.info(f"Receiver: ... for padding to {buffer_size}...")
        # Adjust for iv
        buffer_size += 16
        # logger.info(f"Receiver: ...for iv to: {buffer_size}")
        return buffer_size


    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        iv = chunk[:16]                                     # separate iv
        chunk = chunk[16:]                                  # from the chunk,
        # logger.info(f"Receiver: got chunk with IV:   {iv}")
        cipher = AES.new(self.key, AES.MODE_CBC, iv=iv)     # initiate new cipher,
        chunk = cipher.decrypt(chunk)                       # decrypt,
        # logger.info(f"Receiver: chunk head: {chunk[:10]}")
        # logger.info(f"Receiver: chunk tail: {chunk[-10:]}")
        # logger.info(f"Receiver: chunk length: {len(chunk)}")
        if len(chunk) % AES.block_size != 0:
            chunk = unpad(chunk, AES.block_size)            # unpad,  TODO: this is unreachabe because every padded message will also give modulo = 0! Changing this to a try/except gives bad outputs
        return chunk
    
    def receiver_cleanup(self) -> None:
        return