# CipherCaller example Kyber plugin
#
# You can use this file as reference for implementing plugins that suit your needs

from src.plugins.util.template_plugin import Plugin
from src.benchmarking import TimestampLogger
from time import perf_counter, sleep
from typing import Any
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
class LiboqsAES256(Plugin):

# === COMMON INITIALIZATION === #
    def __init__(self, config: dict) -> None:
        self.main_plugin_config = config.get("plugin", {})
        self.socket_params = config["sockets"]
        self.max_udp_datagram_length = 65507  # <- practical maximum datagram data length

        # Get this plugin's configuration
        if (config_path := self.main_plugin_config.get("config_path", None)) is not None:
            self.this_plugin_config = yaml.safe_load(open(config_path))
        else:
            raise RuntimeError(
                f"{type(self).__name__} did not find path to own configuration in config.yaml! (config.yaml -> plugin -> config_path)"
            )

        logger.info(f"{oqs.get_enabled_kem_mechanisms()}")
        self.kemalg = self.this_plugin_config.get("liboqs_alg_name", None)
        if self.kemalg is None:
            raise ValueError(f"{self.main_plugin_config.get("config_path")}: 'liboqs_alg_name' key or value missing!")
        
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
        if self.kem.length_public_key > self.max_udp_datagram_length:
            for i in range(0, int(self.kem.length_public_key // self.max_udp_datagram_length) + 1):
                sockfd.sendto(key[i*self.max_udp_datagram_length : min((i+1)*self.max_udp_datagram_length, self.kem.length_public_key)], 
                    (self.socket_params["receiver_host"],
                    int(self.socket_params["port"])))
                # logger.info(f"Sent part {i}")
                sleep(0.001)
        else:
            sockfd.sendto(key, 
                (self.socket_params["receiver_host"],
                int(self.socket_params["port"])))
        return

    def sender_key_exchange(self, sockfd: socket.socket, logger_object:TimestampLogger=None) -> None:
        # self.kem = oqs.KeyEncapsulation(self.kemalg)
        logger.debug(f"Generating {self.kem.details["name"]} keypair...")
        if logger_object is not None:
            logger_object.save_timestamp(perf_counter())
        public_key_client = self.kem.generate_keypair()  # public keys match

        logger.debug(f"Transmitting {self.kem.details["name"]} public key...")
        if logger_object is not None:
            logger_object.save_timestamp(perf_counter())
        self.sender_transmit_public_key(sockfd, public_key_client)

        logger.debug("Waiting for symmetric key...")
        ciphertext = sockfd.recvfrom(self.kem.length_ciphertext)[0]  # We don't need the origin address here

        logger.debug("Decapsulating symmetric key...")
        self.symmetric_key = self.kem.decap_secret(ciphertext)
        if logger_object is not None:
            logger_object.save_timestamp(perf_counter())
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

    def sender_get_info(self) -> dict[str, Any] | None:
        return self.kem.details

# === RECEIVER METHODS === #
    def receiver_key_exchange(self, sockfd: socket.socket, logger_object:TimestampLogger=None) -> None:
        # self.kem = oqs.KeyEncapsulation(self.kemalg)
        logger.debug("Waiting for sender's public key...")
        if self.kem.length_public_key > self.max_udp_datagram_length:
            public_key_sender = b''
            # len_sum = 0
            for i in range(0, int(self.kem.length_public_key // self.max_udp_datagram_length) + 1):
                public_key_fragment, sender_address = sockfd.recvfrom(self.max_udp_datagram_length)
                public_key_sender += public_key_fragment
                # len_sum += len(public_key_fragment)
                # logger.info(f"Received part {i} [{len(public_key_fragment)} / {len_sum} / {self.kem.length_public_key}]")
        else:
            public_key_sender, sender_address = sockfd.recvfrom(self.kem.length_public_key)  # public keys match
        if logger_object is not None:
            logger_object.save_timestamp(perf_counter())

        logger.debug(f"Generating and encapsulating AES-256 key ({self.kem.length_shared_secret}B)...")
        ciphertext, self.symmetric_key = self.kem.encap_secret(public_key_sender)

        logger.debug("Sending encapsulated key...")
        sockfd.sendto(ciphertext, sender_address)
        if logger_object is not None:
            logger_object.save_timestamp(perf_counter())
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