import logging  # logs
import pyaudio  # audio I/O
import wave  # wav files
import socket  # web sockets api
import jack  # host audio device I/O, might switch to portaudio but this is more low-level
import sys  # exit()
import time  # performance measurements + sleep
import csv  # performance logging maybe
from src.plugins.loader import load_plugin

logger = logging.getLogger(__name__)

class Sender:
    def __init__(self, config: dict) -> None:
        # Basic transmission
        self.config = config
        self.input_params = config["input"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        self.chunks_sent = bytes(8)  # 32-bit counter (borrowed from TCP)
        # Benchmarking
        if config["benchmarking"].get("log_timestamps", False):  # Note: pyyaml swaps yes, no, on and off to True and False!
            self.benchmark_on = True
            self.benchmark_params = config["benchmarking"]
        else:
            self.benchmark_on = False
        # Plugins
        if config["plugin"].get("use_plugin", False):
            logger.info("Loading plugin...")
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)  # TODO: Stop here or proceed on None?
        else:
            self.use_plugin = False
        # Sender debug
        self.debug_params = config.get("debug", {})
        if self.debug_params.get("sender_output_stream_to_file", False):
            self.debug_write_file = True
        else:
            self.debug_write_file = False


    def increment_chunks_sent_mod(self) -> None:
        self.chunks_sent = (int.to_bytes((int.from_bytes(self.chunks_sent) + 1) % 0xFFFFFFFF, length=8))
        #logger.info(f"chunks_sent: {self.chunks_sent} ({int.from_bytes(self.chunks_sent)})")


    def process_chunk_for_sending(self, chunk: bytes) -> bytes:
        # ...Encrypt...
        if self.use_plugin:
            chunk = self.plugin.sender_encrypt_chunk(chunk)
        # ...Add a squence number...
        chunk = self.chunks_sent + chunk

        return chunk


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
            # Transmit chunks
            while True:
                try:
                    # Read chunk from microphone stream...
                    chunk = microphone_stream.read(self.pyaudio_params["chunk_size"])

                    # ...Write to debug output...
                    if self.debug_write_file:
                        debug_wf.writeframes(chunk)

                    # ...Process...
                    chunk = self.process_chunk_for_sending(chunk)

                    # ...And transmit to receiver
                    self.send_stream_chunk_to_host(chunk, sockfd)  # TODO: Pack chunks_sent into the packet, too!
                    logger.info(f"Sent chunk {int.from_bytes(self.chunks_sent)} [{len(chunk)}]")
                    self.increment_chunks_sent_mod()
                except KeyboardInterrupt:
                    logger.info("Ctrl+C detected, stopping transmission...")
                    break
        
        # Stream file contents to receiver
        elif method == "file":
            logger.info(f"Sending contents of {input_file_path} to {self.socket_params["receiver_host"]}...")
            # Read consecutive chunks...
            while len(chunk := wf.readframes(self.pyaudio_params["chunk_size"])):

                # ...Write to debug output...
                if self.debug_write_file:
                    debug_wf.writeframes(chunk)

                # ...Process...
                chunk = self.process_chunk_for_sending(chunk)

                # ...And transmit to receiver
                self.send_stream_chunk_to_host(chunk, sockfd)
                logger.info(f"Sent chunk {int.from_bytes(self.chunks_sent)} [{len(chunk)}]")
                self.increment_chunks_sent_mod()
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