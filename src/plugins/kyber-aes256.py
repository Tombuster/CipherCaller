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

        self.kemalg = "ML-KEM-512"
        self.kem = oqs.KeyEncapsulation(self.kemalg)
        logger.debug("+----- KEM info -----")
        logger.debug(f"| Name: {self.kem.details["name"]}")
        logger.debug(f"| Version: {self.kem.details["version"]}")
        logger.debug(f"| Claimed NIST level: {self.kem.details["claimed_nist_level"]}")
        logger.debug(f"| Is IND-CCA?: {self.kem.details["is_ind_cca"]}")
        logger.debug(f"| Public key length: {self.kem.details["length_public_key"]}B")
        logger.debug(f"| Secret key length: {self.kem.details["length_secret_key"]}B")
        logger.debug(f"| Ciphertext length: {self.kem.details["length_ciphertext"]}B")
        logger.debug(f"| Shared secret length: {self.kem.details["length_shared_secret"]}B")
        logger.debug(f"| Key pair seed length: {self.kem.details["length_keypair_seed"]}B")
        logger.debug("+--------------------")
        # self.kem.free()
        self.symmetric_key = bytes(1)

# === SENDER METHODS === #
    def sender_transmit_public_key(self, sockfd: socket.socket, key: bytes) -> None:
        sockfd.sendto(key, 
            (self.socket_params["receiver_host"],
             int(self.socket_params["port"])))
        return

    def sender_key_exchange(self, sockfd: socket.socket) -> None:
        # self.kem = oqs.KeyEncapsulation(self.kemalg)

        logger.debug("Generating Kyber keypair...")
        public_key_client = self.kem.generate_keypair()  # public keys match

        logger.debug("Transmitting Kyber public key...")
        self.sender_transmit_public_key(sockfd, public_key_client)

        logger.debug("Waiting for symmetric key...")
        ciphertext = sockfd.recvfrom(self.kem.length_ciphertext)[0]  # We don't need the origin address here

        logger.debug("Decapsulating symmetric key...")
        self.symmetric_key = self.kem.decap_secret(ciphertext)
        logger.debug("Sender key exchange finished!")
        logger.debug(f"Sender key:   {self.symmetric_key}")
        # self.kem.free()
        return

    
    def sender_encrypt_chunk(self, chunk: bytes) -> bytes:
        cipher = AES.new(self.symmetric_key, AES.MODE_CBC)
        pad_flag = 0x00
        if len(chunk) % AES.block_size != 0:
            pad_flag = 0x01
            chunk = pad(chunk, AES.block_size)
        chunk = cipher.encrypt(chunk)
        chunk = cipher.iv + chunk
        chunk = int.to_bytes(pad_flag) + chunk
        return chunk
    
    def sender_cleanup(self) -> None:
        self.kem.free()
        return


# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket.socket) -> None:
        # self.kem = oqs.KeyEncapsulation(self.kemalg)

        logger.debug("Waiting for sender's public key...")
        public_key_sender, sender_address = sockfd.recvfrom(self.kem.length_public_key)  # public keys match

        logger.debug(f"Generating and encapsulating AES-256 key ({self.kem.length_shared_secret}B)...")
        ciphertext, self.symmetric_key = self.kem.encap_secret(public_key_sender)

        logger.debug("Sending encapsulated key...")
        sockfd.sendto(ciphertext, sender_address)
        logger.debug("Receiver key exchange finished!")
        logger.debug(f"Receiver key: {self.symmetric_key}")
        # self.kem.free()
        return
    
    def receiver_extend_buffer(self, buffer_size: int) -> int:
        if buffer_size % AES.block_size != 0:
            buffer_size += (buffer_size % AES.block_size)
            buffer_size += 16
            buffer_size += 1
        return buffer_size

    def receiver_decrypt_chunk(self, chunk: bytes) -> bytes:
        pad_flag = chunk[0]
        iv = chunk[1:17]                                     # separate iv
        chunk = chunk[17:]        
        cipher = AES.new(self.symmetric_key, AES.MODE_CBC, iv=iv)
        chunk = cipher.decrypt(chunk)
        if pad_flag:
            chunk = unpad(chunk, AES.block_size)
        return chunk
    
    def receiver_cleanup(self) -> None:
        self.kem.free()
        return