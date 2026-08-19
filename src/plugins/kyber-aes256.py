# CipherCaller example Kyber plugin
#
# You can use this file as reference for implementing plugins that suit your needs

from src.plugins.util.template_plugin import Plugin
import logging
import socket
import yaml
# The imports below must be included in src/plugins/util/plugin-requirements.txt
import oqs  # look into licenses
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)

# Functionality based on https://github.com/open-quantum-safe/liboqs-python/blob/main/examples/kem.py
class KyberAES256(Plugin):

# === COMMON INITIALIZATION === #
    def __init__(self, config: dict) -> None:
        self.main_plugin_config = config.get("plugin", {})
        self.socket_params = config["sockets"]

        # Get this plugin's configuration
        if (config_path := self.main_plugin_config.get("config_path", None)) is not None:
            self.this_plugin_config = yaml.safe_load(open(config_path))
        else:
            raise RuntimeError(
                f"{type(self).__name__} did not find path to own configuration in config.yaml! (config.yaml -> plugin -> config_path)"
            )

        self.kemalg = "ML-KEM-512"
        self.kem = oqs.KeyEncapsulation(self.kemalg)
        logger.info("+----- KEM INFO -----")
        logger.info(f"| Name: {self.kem.details["name"]}")
        logger.info(f"| Version: {self.kem.details["version"]}")
        logger.info(f"| Claimed NIST level: {self.kem.details["claimed_nist_level"]}")
        logger.info(f"| Is IND-CCA?: {self.kem.details["is_ind_cca"]}")
        logger.info(f"| Public key length: {self.kem.details["length_public_key"]}B")
        logger.info(f"| Secret key length: {self.kem.details["length_secret_key"]}B")
        logger.info(f"| Ciphertext length: {self.kem.details["length_ciphertext"]}B")
        logger.info(f"| Shared secret length: {self.kem.details["length_shared_secret"]}B")
        logger.info(f"| Key pair seed length: {self.kem.details["length_keypair_seed"]}B")
        logger.info("+--------------------")
        self.symmetric_key = bytes(1)

# === SENDER METHODS === #
    def sender_transmit_public_key(self, sockfd: socket.socket, key: bytes) -> None:
        sockfd.sendto(key, 
            (self.socket_params["receiver_host"],
             int(self.socket_params["port"])))
        return

    def sender_key_exchange(self, sockfd: socket.socket) -> None:
        logger.info("Generating Kyber keypair...")
        public_key_client = self.kem.generate_keypair()  # public keys match

        logger.info("Transmitting Kyber public key...")
        self.sender_transmit_public_key(sockfd, public_key_client)

        logger.info("Waiting for symmetric key...")
        ciphertext = sockfd.recvfrom(self.kem.length_ciphertext)[0]  # We don't need the origin address here

        logger.info("Decapsulating symmetric key...")
        self.symmetric_key = self.kem.decap_secret(ciphertext)
        logger.info("Sender key exchange finished!")
        logger.info(f"Sender key:   {self.symmetric_key}")
        self.kem.free()
        return

    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        cipher = AES.new(self.symmetric_key, AES.MODE_CBC)
        if len(chunk) % AES.block_size != 0:
            chunk = pad(chunk, AES.block_size)
        chunk = cipher.encrypt(chunk)
        chunk = cipher.iv + chunk
        return chunk
    
    def sender_cleanup(self) -> None:
        return


# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket.socket) -> None:
        logger.info("Waiting for sender's public key...")
        public_key_sender, sender_address = sockfd.recvfrom(self.kem.length_public_key)  # public keys match

        logger.info(f"Generating and encapsulating AES-256 key ({self.kem.length_shared_secret}B)...")
        ciphertext, self.symmetric_key = self.kem.encap_secret(public_key_sender)

        logger.info("Sending encapsulated key...")
        sockfd.sendto(ciphertext, sender_address)
        logger.info("Receiver key exchange finished!")
        logger.info(f"Receiver key: {self.symmetric_key}")
        self.kem.free()
        return
    
    def receiver_extend_buffer(self, buffer_size: int) -> int:
        if buffer_size % AES.block_size != 0:
            buffer_size += (buffer_size % AES.block_size)
            buffer_size += 16
        return buffer_size

    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        iv = chunk[:16]
        chunk = chunk[16:]
        cipher = AES.new(self.symmetric_key, AES.MODE_CBC, iv=iv)
        chunk = cipher.decrypt(chunk)
        if len(chunk) % AES.block_size != 0:
            chunk = unpad(chunk, AES.block_size)  # unpad,  TODO: this is unreachabe because every padded message will also give modulo = 0! Changing this to a try/except gives bad outputs
        return chunk
    
    def receiver_cleanup(self) -> None:
        return