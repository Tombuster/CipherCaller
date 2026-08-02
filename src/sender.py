import logging
import pyaudio
import socket
import wave
import jack  # For host audio device I/O, might switch to portaudio but this is more low-level
import sys
import time
import csv
from src.plugins.loader import load_plugin

logger = logging.getLogger(__name__)

class Sender:
    def __init__(self, config: dict) -> None:
        self.input_params = config["input"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        self.benchmark_params = config["benchmarking"]
        if config["plugin"].get("use_plugin", "no") == "yes":
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)  # TODO: Stop here or proceed on None?
        else:
            self.use_plugin = False

        # Get sender debug config
        self.debug_params = config.get("debug", {})
        if self.debug_params.get("sender_output_stream_to_file", "no") == "yes":
            self.debug_write_file = True
        else:
            self.debug_write_file = False


    def send_stream_chunk_to_host(self, chunk: bytes, sockfd: socket.socket) -> None:
        sockfd.sendto(chunk, 
            (self.socket_params["receiver_host"],
             int(self.socket_params["port"])))
        return


    def run(self):
    # === SET UP === #
        # Set up sender socket
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set up input related I/O
        method = self.input_params.get("method", "file")
        input_file_path = self.input_params.get("file_path", "/media/input/input.wav")

        if method == "microphone":
        # # TODO: Set up JACK client
        #     jack_client = jack.Client("CipherCaller_mic_input")
        #     jack_input = jack_client.inports.register('input_1')
        #     print(jack_client.get_ports())

            # Set up microphone data stream
            # Based on https://people.csail.mit.edu/hubert/pyaudio/#record-example
            p = pyaudio.PyAudio()
            microphone_stream = p.open(format=pyaudio.get_format_from_width(self.pyaudio_params["sample_width_bytes"]),
                channels=self.pyaudio_params["channels"],
                rate=self.pyaudio_params["rate"],
                input=True,
                frames_per_buffer=self.pyaudio_params["chunk_size"])
        # Set up wave file input
        elif method == "file":
            try:
                wf = wave.open(input_file_path, 'r')
            except FileNotFoundError:
                logger.error(f"Sender error: File {input_file_path} not found!")
                sys.exit(2)
            except PermissionError:
                logger.error(f"Sender error: Permission denied for file {input_file_path}!")
                sys.exit(3)
            logger.info(f"Opened file '{input_file_path}' successfully!")
            # Print file info
            logger.info("+--- INPUT FILE STATS ---")
            logger.info(f"| File sample width: {wf.getsampwidth()}, expected (config value): {self.pyaudio_params["sample_width_bytes"]}")
            logger.info(f"| File framerate: {wf.getframerate()}, expected (config value): {self.pyaudio_params["rate"]}")
            logger.info(f"| File channels: {wf.getnchannels()}, expected (config value): {self.pyaudio_params["channels"]}")
            logger.info(f"| File compression type: {wf.getcompname()}")
            logger.info("+------------------------")

        # Invalid mode supplied
        else:
            logger.error(f"Sender error: Unsupported operation mode: {method}! Please check the value of config.yaml -> input -> method, and refer to the documentation for supported values.")
            sys.exit(1)

        # Debug
        if self.debug_write_file:
            output_file_path = self.input_params.get("debug_out_file_path", "/media/output/sender_output.wav")
            try:
                debug_wf = wave.open(output_file_path, 'w')
            except FileNotFoundError:
                logger.error(f"Receiver error: File {output_file_path} not found!")
                sys.exit(2)
            except PermissionError:
                logger.error(f"Receiver error: Permission denied for file {output_file_path}!")
                sys.exit(3)
            
            debug_wf.setnchannels(self.pyaudio_params["channels"])
            debug_wf.setsampwidth(self.pyaudio_params["sample_width_bytes"])
            debug_wf.setframerate(self.pyaudio_params["rate"])

        # Finish set up
        logger.info("Sender setup complete!")


    # === KEY EXCHANGE === #
        if self.use_plugin:
            self.plugin.sender_key_exchange(sockfd)

    # === TRANSMIT === #
        logger.info(f"Waiting {self.socket_params["sender_delay_ms"]/1000} seconds to allow for receiver to bind... (Change in config.yaml -> sockets -> sender_delay_ms)")
        time.sleep(self.socket_params["sender_delay_ms"]/1000)

        # Stream microphone input to receiver
        if method == "microphone":
            # Inform user that transmission will start shortly
            logger.info("Microphone transmission will begin after the following countdown. Press Ctrl+C to stop transmitting.")
            for i in range(5, 0, -1):
                logger.info(f"{i}...")
                time.sleep(1)
            logger.info("Sending audio. Press Ctrl+C to stop")
            while True:
                try:
                    # Read chunk from microphone stream...
                    chunk = microphone_stream.read(self.pyaudio_params["chunk_size"])

                    # ...Write to debug output...
                    if self.debug_write_file:
                        debug_wf.writeframes(chunk)

                    # ...Encrypt it...
                    if self.use_plugin:
                        chunk = self.plugin.sender_encrypt_chunk(chunk)

                    # ...And transmit to receiver
                    self.send_stream_chunk_to_host(chunk, sockfd)
                except KeyboardInterrupt:
                    break
        
        # Stream file contents to receiver
        elif method == "file":
            logger.info(f"Sending contents of {input_file_path} to {self.socket_params["receiver_host"]}...")
            # Read consecutive chunks...
            while len(chunk := wf.readframes(self.pyaudio_params["chunk_size"])):
                logger.info(f"Raw chunk size: {len(chunk)}")
                # ...Write to debug output...
                if self.debug_write_file:
                    debug_wf.writeframes(chunk)

                # ...Encrypt them...
                if self.use_plugin:
                    self.plugin.sender_encrypt_chunk(chunk)
                    logger.info(f"Encrypted chunk size: {len(chunk)}")
                # ...And transmit to receiver
                self.send_stream_chunk_to_host(chunk, sockfd)
                # logger.info(f"Sent chunk length: {len(chunk)}")
                # Then wait a bit to simulate real-time playback
                # sleep(0.01)
        
        # Notify user about ending transmission
        logger.info("Transmission finished!")

    # === CLEAN UP === #
        if self.use_plugin:  # Plugin
            self.plugin.sender_cleanup()
        if method == "microphone":  
            # PyAudio
            microphone_stream.close()
            p.terminate()
            # TODO: JACK

        elif method == "file":  # Wave
            wf.close()
        sockfd.close()  # Sockets
        sys.exit()