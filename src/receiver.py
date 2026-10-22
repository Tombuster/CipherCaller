import logging  # logs
import pyaudio  # audio I/O
import wave  # wav files
import socket  # web sockets api
import sys  # exit()
import time  # performance measurements + sleep
import subprocess  # FFmpeg pipe
from src.plugins.util.loader import load_plugin
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
        # FFmpeg
        if config["ffmpeg"].get("use_ffmpeg", False):
            self.use_ffmpeg = True
            self.ffmpeg_params = config["ffmpeg"]
        # Plugins
        if config["plugin"].get("use_plugin", False):
            logger.info("Loading plugin...")
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)
        else:
            self.use_plugin = False
        # Sockets recvfrom buffer size
        self.buffer_size = (int(self.pyaudio_params["chunk_size"])  # calculate base buffer length as (chunk * channels * sample width)
                            * int(self.pyaudio_params["channels"])
                            * int(self.pyaudio_params["sample_width_bytes"]))
        # Extend buffer size to acommodate paddings, etc.
        if self.use_plugin:
            self.buffer_size = self.plugin.receiver_extend_buffer(self.buffer_size)
        self.buffer_size += 8  # Add space for sequence number


    def build_ffmpeg_base(self):
        if self.ffmpeg_params.get("sample_format", None) is not None:
            ffmpeg_base = [
                "ffmpeg", "-hide_banner",
                "-f", f"{self.ffmpeg_params["sample_format"]}",
                "-i", "pipe:0",
                "-c", "copy",
                "-y", f"{self.output_params.get("file_path", "/media/output/output.wav")}"
            ]
        else:
            logger.error("FFmpeg argument error: 'sample_format' key missing or invalid value supplied!")
            exit()  # TODO: set exit code
        return ffmpeg_base


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
        # Set up pyaudio output stream
            p = pyaudio.PyAudio()
            pyaudio_output_stream = p.open(format=pyaudio.get_format_from_width(self.pyaudio_params["sample_width_bytes"]),
                channels=self.pyaudio_params["channels"],
                rate=self.pyaudio_params["rate"],
                output=True,
                output_device_index=self.output_params.get("output_device_index"))
            logger.info("+----- OUTPUT DEVICES INFO -----")
            # https://stackoverflow.com/a/39677871 modified for logger.info
            info = p.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            selected = self.output_params.get("output_device_index")
            for i in range(0, numdevices):
                if (p.get_device_info_by_host_api_device_index(0, i).get('maxOutputChannels')) > 0:  # is input device
                    device_info = p.get_device_info_by_host_api_device_index(0, i)
                    logger.info(f"| {">" if i == selected else " "} Output Device id {i}: {"(SELECTED)" if i == selected else ""}")
                    logger.info(f"|     name: {device_info.get('name')}")
                    logger.info(f"|     sample rate: {device_info.get('defaultSampleRate')}")
            logger.info("|")
            logger.info("| (config.yaml -> output -> output_device_index)")
            logger.info("+------------------------------")
        
        # Set up wav file output
        if method == "file" or method == "both":
            if self.use_ffmpeg:
                proc = subprocess.Popen(self.build_ffmpeg_base(), stdin=subprocess.PIPE)
            if not self.use_ffmpeg:
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

        if method not in ["file", "playback", "both"]:  # Invalid mode supplied
            logger.error(f"Receiver error: Unsupported operation mode: {method}! Please check the value of config.yaml -> output -> method, and refer to the documentation for supported values.")
            sys.exit(1)

        # Set up performance logging
        if self.benchmark_on:
            benchmark_logger = TimestampLogger(self.config, "receiver")
            benchmark_logger.write_headers(["Sequence number", "Chunk received", "Chunk processed", "Chunk played"])
            logger.info(f"Set up performance logging into file '{benchmark_logger.get_file_name()}'")

        # Finish set up
        logger.info("Receiver setup complete!")

    # === KEY EXCHANGE === #
        if self.use_plugin:
            self.plugin.receiver_key_exchange(sockfd)
        
    # === RECEIVE === #
        # Receive transmitted chunk...
        while True:
            try:
                data = self.receive_stream_chunk_from_host(sockfd)
            except socket.timeout:
                logger.warning(f"Receiver warning: Socket timeout ({socket_timeout} s) exceeded! (config.yaml -> sockets -> receiver_timeout_ms)")
                break

            # ...separate the sequence number...
            sequence_number = int.from_bytes(data[:8])
            if sequence_number == 0xFFFFFFFF:
                logger.info("Received EOF sequence (0xFFFFFFFF)")
                break
            chunk = data[8:]

            # ...log reception timestamp...
            if self.benchmark_on:
                benchmark_logger.new_line(sequence_number)
                benchmark_logger.save_timestamp(time.perf_counter())
            # if sequence_number == (self.last_received + 1) % 0xFFFFFFFF:  # Received next chunk
            logger.info(f"Received chunk {sequence_number}!")
           
            # ...process by plugin if specified...
            if self.use_plugin:
                chunk = self.plugin.receiver_decrypt_chunk(chunk)

            # ...log processing end timestamp...
            if self.benchmark_on:
                benchmark_logger.save_timestamp(time.perf_counter())

            # ...and output result
            if method == "playback" or method == "both":
                pyaudio_output_stream.write(chunk)
            if method == "file" or method == "both":
                if self.use_ffmpeg:
                    proc.stdin.write(chunk)
                    proc.stdin.flush()
                else:
                    wf.writeframes(chunk)
            benchmark_logger.save_timestamp(time.perf_counter())

            # Commit timestamps
            benchmark_logger.write_line()

    # === CLEAN UP === #
        if method == "file" or method == "both":  # Wave
            if self.use_ffmpeg:
                proc.stdin.flush()
                proc.stdin.close()
                ret = proc.wait()
                if ret != 0:
                    logger.error("FFmpeg exited with code %d", ret)
            if not self.use_ffmpeg:
                wf.close()

        if self.use_plugin:
            self.plugin.receiver_cleanup()

        if method == "playback" or method == "both":
            # PyAudio
            pyaudio_output_stream.close()
            p.terminate()
            
        sockfd.close()  # Sockets
        sys.exit()