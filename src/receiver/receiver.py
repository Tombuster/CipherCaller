import logging
import socket
import pyaudio
import wave
import jack
import sys
from src.plugins.loader import load_plugin

# Debug puropses
from time import sleep

logger = logging.getLogger(__name__)

class Receiver:
    def __init__(self, config: dict) -> None:
        self.output_params = config["output"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        if config["plugin"].get("use_plugin", "no") == "yes":
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)  # TODO: Stop here or proceed on None?
        else:
            self.use_plugin = False

    def receive_stream_chunk_from_host(self, sockfd: socket.socket) -> bytes:
        chunk = sockfd.recvfrom(6*int(self.pyaudio_params["chunk_size"]))[0]  # Discard sender address - only simplex communication
        return chunk


    def run(self):
    # === SET UP === #
        # Set up receiver socket
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socket_timeout = float(self.pyaudio_params.get("receiver_timeout_ms", 10000)/1000)
        sockfd.settimeout(socket_timeout)
        sockfd.bind((self.socket_params.get("receiver_address", ""), int(self.socket_params["port"])))
        logger.info(f"Receiver socket successfully bound to address '{self.socket_params.get("receiver_address", "")}' port {int(self.socket_params["port"])}")
        
        # Set up file output related I/O
        method = self.output_params.get("method", "file")
        output_file_path = self.output_params.get("file_path", "/media/output/output.wav")

        if method == "playback" or method == "both":
        # TODO: Set up JACK client


        # Set up pyaudio output stream
            p = pyaudio.PyAudio()
            pyaudio_output_stream = p.open(format=pyaudio.get_format_from_width(self.pyaudio_params["sample_width_bytes"]),
                channels=self.pyaudio_params["channels"],
                rate=self.pyaudio_params["rate"],
                output=True,
                output_device_index=0)
        
        # Set up wav file output
        if method == "file" or method == "both":
            try:
                wf = wave.open(output_file_path, 'wb')
            except FileNotFoundError:
                logger.error(f"Receiver error: File {output_file_path} not found!")
                sys.exit(2)
            except PermissionError:
                logger.error(f"Receiver error: Permission denied for file {output_file_path}!")
                sys.exit(3)

            wf.setnchannels(self.pyaudio_params["channels"])
            wf.setsampwidth(self.pyaudio_params["sample_width_bytes"])
            wf.setframerate(self.pyaudio_params["rate"])

        # Invalid mode supplied
        if method not in ["file", "playback", "both"]:
            logger.error(f"Receiver error: Unsupported operation mode: {method}! Please check the value of config.yaml -> output -> method, and refer to the documentation for supported values.")
            sys.exit(1)

        # Finish set up
        logger.info("Receiver setup complete")

    # === KEY EXCHANGE === #
        if self.use_plugin:
            self.plugin.receiver_key_exchange(sockfd)
        
    # === RECEIVE === #
        # Receive transmitted chunk...
        exit_loop = False
        while not exit_loop:
            try:
                chunk = self.receive_stream_chunk_from_host(sockfd)
                # logger.info(f"Received chunk! expected length:{self.pyaudio_params["chunk_size"]}, got {len(chunk)}")
            except socket.timeout:
                logger.warning(f"Receiver warning: Socket timeout ({socket_timeout} s) exceeded!")
                exit_loop = True
                
            # ...process by plugin if specified...
            if self.use_plugin:
                chunk = self.plugin.receiver_decrypt_chunk(chunk)

            # ...and output result
            if method == "playback" or method == "both":
                pyaudio_output_stream.write(chunk)
            if method == "file" or method == "both":
                wf.writeframes(chunk)


    # === CLEAN UP === #
        if self.use_plugin:  # Plugin
            self.plugin.receiver_cleanup()
        if method == "playback" or method == "both":
            # PyAudio
            pyaudio_output_stream.close()
            p.terminate()
            # TODO: JACK

        if method == "file" or method == "both":  # Wave
            wf.close()
        sockfd.close()  # Sockets
        sys.exit()