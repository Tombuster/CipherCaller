import logging  # logs
import pyaudio  # audio I/O
import wave  # wav files
import socket  # web sockets api
import jack  # host audio device I/O, might switch to portaudio but this is more low-level
import sys  # exit()
import time  # performance measurements + sleep
import csv  # performance logging maybe
from src.plugins.loader import load_plugin
from src.benchmarking import TimestampLogger


logger = logging.getLogger(__name__)

class Receiver:
    def __init__(self, config: dict) -> None:
        # Basic transmission
        self.config = config
        self.output_params = config["output"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        self.last_received = 0  # Sequence number of last received chunk

        # Benchmarking
        if config["benchmarking"].get("log_timestamps", False):
            self.benchmark_on = True
            self.benchmark_params = config["benchmarking"]
        else:
            self.benchmark_on = False

        # Plugins
        if config["plugin"].get("use_plugin", False):
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)  # TODO: Stop here or proceed on None?
        else:
            self.use_plugin = False

        # Sockets recvfrom buffer size
        self.buffer_size = (int(self.pyaudio_params["chunk_size"])  # calculate base buffer length as (chunk * channels * sample width)
                            * int(self.pyaudio_params["channels"])
                            * int(self.pyaudio_params["sample_width_bytes"]))
        # Extend buffer size to acommodate paddings, etc.
        if self.use_plugin:
            self.buffer_size = self.plugin.receiver_extend_buffer(self.buffer_size)
        # Add space for sequence number
        self.buffer_size += 8
        # logger.info(f"===> Final buffer size: {self.buffer_size} <===")


    def receive_stream_chunk_from_host(self, sockfd: socket.socket) -> bytes:
        chunk = sockfd.recvfrom(self.buffer_size)[0]  # discard sender address - only simplex communication
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

        # TODO: Set up performance logging
        # if self.benchmark_on:
        #     # Create timestamp logger with appropriate file name
        #     timestamp_logger = TimestampLogger(self.config)

        #     # Write headers in first line

        # Finish set up
        logger.info("Receiver setup complete!")

    # === KEY EXCHANGE === #
        if self.use_plugin:
            self.plugin.receiver_key_exchange(sockfd)
        
    # === RECEIVE === #
        # Receive transmitted chunk...
        exit_loop = False
        while not exit_loop:
            try:
                data = self.receive_stream_chunk_from_host(sockfd)
            except socket.timeout:
                logger.warning(f"Receiver warning: Socket timeout ({socket_timeout} s) exceeded!")
                exit_loop = True

            # ...separate the sequence number...
            sequence_number = int.from_bytes(data[:8])
            chunk = data[8:]
            logger.info(f"Received chunk {sequence_number}!")
                
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
        # if self.benchmark_on:
        #     timestamp_logger.close()
        sys.exit()