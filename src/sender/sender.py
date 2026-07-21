import logging
import pyaudio
import socket
import wave
import sys
from time import sleep
from src.plugins.loader import load_plugin

logger = logging.getLogger(__name__)

class Sender:
    def __init__(self, config: dict) -> None:
        self.input_params = config["input"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        if config["plugin"].get("use_plugin", "no") == "yes":
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)  # TODO: Stop here or proceed on None?
        else:
            self.use_plugin = False

    def send_stream_chunk_to_host(self, socket_params: dict, chunk: bytes, sockfd: socket.socket) -> None:
        sockfd.sendto(chunk, 
            (socket_params["receiver_host"],
             int(socket_params["port"])))
        return


    def run(self):
    # === SET UP === #
        # Set up sender socket
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set up input related I/O
        method = self.input_params.get("method", "file")
        input_file_path = self.input_params.get("file_path", "/media/input/input.wav")

        # Set up microphone data stream
        # Based on https://people.csail.mit.edu/hubert/pyaudio/#record-example
        if method == "microphone":
            p = pyaudio.PyAudio()
            microphone_stream = p.open(format=pyaudio.paInt16,
                channels=self.pyaudio_params["channels"],
                rate=self.pyaudio_params["rate"],
                input=True,
                frames_per_buffer=self.pyaudio_params["chunk_size"])
            
        # Set up wave file input
        elif method == "file":
            try:
                wf = wave.open(input_file_path, 'rb')
            except FileNotFoundError:
                logger.error(f"Sender error: File {input_file_path} not found!")
                sys.exit(2)
            except PermissionError:
                logger.error(f"Sender error: Permission denied for file {input_file_path}!")
                sys.exit(3)

        # Invalid mode supplied
        else:
            logger.error(f"Sender error: Unsupported operation mode: {method}! Please check the value of config.yaml -> input -> method, and refer to the documentation for supported values.")
            sys.exit(1)

        # Finish set up
        logger.info("Sender setup complete!")


    # === KEY EXCHANGE === #
        if self.use_plugin:
            self.plugin.sender_key_exchange()

    # === TRANSMIT === #
        logger.info(f"Waiting {self.socket_params["sender_delay_ms"]/1000} seconds to allow for receiver to bind... (Change in config.yaml -> sockets -> sender_delay_ms)")
        sleep(self.socket_params["sender_delay_ms"]/1000)

        # Stream microphone input to receiver
        if method == "microphone":
            # Inform user that transmission will start shortly
            logger.info("Microphone transmission will begin after the following countdown. Press Ctrl+C to stop transmitting.")
            for i in range(5, 0, -1):
                logger.info(f"{i}...")
                sleep(1)
            logger.info("Sending audio. Press Ctrl+C to stop")
            while True:
                try:
                    # Read chunk from microphone stream...
                    chunk = microphone_stream.read(self.pyaudio_params["chunk_size"])

                    # ...Encrypt it...
                    if self.use_plugin:
                        chunk = self.plugin.sender_encrypt_chunk(chunk)

                    # ...And transmit to receiver
                    self.send_stream_chunk_to_host(self.socket_params, chunk, sockfd)
                except KeyboardInterrupt:
                    break
        
        # Stream file contents to receiver
        elif method == "file":
            logger.info(f"Sending contents of {input_file_path} to {self.socket_params["receiver_host"]}...")
            # Read consecutive chunks...
            while len(chunk := wf.readframes(self.pyaudio_params["chunk_size"])):
                # ...Encrypt them...
                if self.use_plugin:
                    self.plugin.sender_encrypt_chunk(chunk)
                # ...And transmit to receiver
                self.send_stream_chunk_to_host(self.socket_params, chunk, sockfd)
        
        # Notify user about ending transmission
        logger.info("Transmission finished!")

    # === CLEAN UP === #
        if self.use_plugin:  # Plugin
            self.plugin.sender_cleanup()
        if method == "microphone":  # PyAudio
            microphone_stream.close()
            p.terminate()
        elif method == "file":  # Wave
            wf.close()
        sockfd.close()  # Sockets
        sys.exit()