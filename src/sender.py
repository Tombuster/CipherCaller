import logging  # logs
import pyaudio  # audio I/O
import wave  # wav files
import socket  # web sockets api
import sys  # exit()
import time  # performance measurements + sleep
import subprocess  # FFmpeg pipe
import os  # os.read() for reading data chunks from ffmpeg pipe
from src.plugins.util.loader import load_plugin
from src.benchmarking import TimestampLogger


logger = logging.getLogger(__name__)

class Sender:
    def __init__(self, config: dict) -> None:
        # Basic transmission
        self.config = config
        self.input_params = config["input"]
        self.pyaudio_params = config["pyaudio"]
        self.socket_params = config["sockets"]
        self.simulate_realtime = self.input_params.get("simulate_realtime", False)
        self.chunks_sent = bytes(8)  # 32-bit counter (borrowed from TCP)
        self.ideal_chunk_time = self.pyaudio_params.get("chunk_size") / self.pyaudio_params.get("rate")
        # Benchmarking
        if config["benchmarking"].get("log_timestamps", False):  # Note: pyyaml swaps yes, no, on and off to True and False!
            self.benchmark_on = True
            self.benchmark_params = config["benchmarking"]
            self.benchmark_logger = TimestampLogger(self.config, "sender")
        else:
            self.benchmark_on = False
        # Plugins
        if config["plugin"].get("use_plugin", False):
            logger.info("Loading plugin...")
            self.use_plugin = True
            self.plugin_params = config["plugin"]
            self.plugin = load_plugin(self.config)
        else:
            self.use_plugin = False
        # Sender debug
        self.debug_params = config.get("debug", {})
        if self.debug_params.get("sender_output_stream_to_file", False):
            self.debug_write_file = True
        else:
            self.debug_write_file = False
        # FFmpeg
        if config["ffmpeg"].get("use_ffmpeg", False):
            self.use_ffmpeg = True
            self.ffmpeg_params = config["ffmpeg"]


    def build_ffmpeg_base(self) -> list[str]:
        ffmpeg_base = ["ffmpeg", "-hide_banner"]

        if self.ffmpeg_params.get("simulate_realtime", True):
            ffmpeg_base.append("-re")  # realtime simulation

        ffmpeg_base.append("-i")
        ffmpeg_base.append(f"media/input/{self.input_params.get("file_name", "input.wav")}")

        if self.ffmpeg_params.get("sample_format", None) is not None:
            ffmpeg_base.append("-f") 
            ffmpeg_base.append(self.ffmpeg_params["sample_format"])
        else:
            logger.error("FFmpeg argument error: 'sample_format' key missing or invalid value supplied!")
            exit()  # TODO: set exit code

        if self.ffmpeg_params.get("codec", None) is not None:
            ffmpeg_base.append("-c:a") 
            ffmpeg_base.append(self.ffmpeg_params["codec"])
        else:
            logger.error("FFmpeg argument error: 'codec' key missing or invalid value supplied!")
            exit()  # TODO: set exit code

        if self.ffmpeg_params.get("sample_rate", None) is not None:
            ffmpeg_base.append("-ar") 
            ffmpeg_base.append(str(self.ffmpeg_params["sample_rate"]))
        else:
            logger.error("FFmpeg argument error: 'sample_rate' key missing or invalid value supplied!")
            exit()  # TODO: set exit code

        if self.ffmpeg_params.get("channels", None) is not None:
            ffmpeg_base.append("-ac") 
            ffmpeg_base.append(str(self.ffmpeg_params["channels"]))
        else:
            logger.error("FFmpeg argument error: 'channels' key missing or invalid value supplied!")
            exit()  # TODO: set exit code
        ffmpeg_base.append("pipe:1")
        return ffmpeg_base

    
    def increment_chunks_sent_mod(self) -> None:
        self.chunks_sent = (int.to_bytes((int.from_bytes(self.chunks_sent) + 1) % 0xFFFFFFFE, length=8))
        #logger.info(f"chunks_sent: {self.chunks_sent} ({int.from_bytes(self.chunks_sent)})")


    def process_chunk_for_sending(self, chunk: bytes) -> bytes:
        '''Run chunk through plugin, add sequence number and write timestamp'''
        # ...Encrypt...
        if self.use_plugin:
            chunk = self.plugin.sender_encrypt_chunk(chunk)
        # ...Add a squence number...
        chunk = self.chunks_sent + chunk
        # ...Log timestamp...
        if self.benchmark_on:
            self.benchmark_logger.save_timestamp(time.perf_counter())
        return chunk


    def send_stream_chunk_to_host(self, chunk: bytes, sockfd: socket.socket) -> None:
        sockfd.sendto(chunk, 
            (self.socket_params["receiver_host"],
             int(self.socket_params["port"])))
        return


    def realtime_sleep(self, read_start: float, read_end: float) -> None:  # TODO: needs some tweaking, sometimes sleeps too long
        # read_start and read_end - fractional seconds from time.perf_counter()
        read_time = read_end - read_start
        if read_time > self.ideal_chunk_time:  # took longer to read & process than real-time input requires
            logger.warning(f"Chunk exceeded real-time processing time window! Time: {read_time}s, Target: {self.ideal_chunk_time}s")
            return
        logger.info(f"Chunk processing time: {read_time}s, target: {self.ideal_chunk_time}s")
        logger.info(f"Delaying next chunk by {self.ideal_chunk_time - read_time} s")
        time.sleep(self.ideal_chunk_time - read_time)  # TODO: Determine sleep duration
        return


    def send_file_ffmpeg(self, sockfd) -> None:
        proc = subprocess.Popen(self.ffmpeg_base, stdout=subprocess.PIPE)
        try:
            fd = proc.stdout.fileno()
            while True:
                # Get chunk
                try:
                    chunk = os.read(fd, self.ffmpeg_params["chunk_size"])
                except OSError as exception:
                    logger.error(f"Read from FFmpeg pipe failed: {exception}")
                    break
                if not chunk:  # EOF reached
                    break

                # Log timestamp
                if self.benchmark_on:
                    self.benchmark_logger.new_line(int.from_bytes(self.chunks_sent))
                    self.benchmark_logger.save_timestamp(time.perf_counter())

                chunk = self.process_chunk_for_sending(chunk)
                self.send_stream_chunk_to_host(chunk, sockfd)

                # Log final sender timestamp
                if self.benchmark_on:
                    self.benchmark_logger.save_timestamp(time.perf_counter())
                    self.benchmark_logger.write_line()

                logger.info(f"Sent chunk {int.from_bytes(self.chunks_sent)} [{len(chunk)}B]")
                self.increment_chunks_sent_mod()
        finally:
            proc.stdout.close()
            ret = proc.wait()

        if ret != 0:
            logger.error("FFmpeg exited with code %d", ret)


    def send_file_proprietary(self, sockfd, wf, debug_wf) -> None:
        if self.simulate_realtime:
            chunk_start = time.perf_counter()
        # Read consecutive chunks...
        while len(chunk := wf.readframes(self.pyaudio_params["chunk_size"])):
            # ...Log timestamp...
            if self.benchmark_on:
                self.benchmark_logger.new_line(int.from_bytes(self.chunks_sent))
                self.benchmark_logger.save_timestamp(time.perf_counter())
                
            # ...Write to debug output...
            if self.debug_write_file:
                debug_wf.writeframes(chunk)

            # ...Process...
            chunk = self.process_chunk_for_sending(chunk)
            # ...And transmit to receiver
            self.send_stream_chunk_to_host(chunk, sockfd)
            # Log final sender timestamp
            if self.benchmark_on:
                self.benchmark_logger.save_timestamp(time.perf_counter())
                self.benchmark_logger.write_line()
                
            logger.info(f"Sent chunk {int.from_bytes(self.chunks_sent)} [{len(chunk)}B]")
            self.increment_chunks_sent_mod()
            # logger.info(f"Sent chunk length: {len(chunk)}")
                
            if self.simulate_realtime:
                chunk_end = time.perf_counter()
                self.realtime_sleep(chunk_start, chunk_end)
                chunk_start = time.perf_counter()

    def send_eof(self, sockfd) -> None:
        self.send_stream_chunk_to_host(int.to_bytes(0xFFFFFFFF, 4), sockfd)

    def run_transmission(self) -> None:
    # === SET UP === #
        # Set up sender socket
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Set up input related I/O
        method = self.input_params.get("method", "file")
        input_file_path = f"media/input/{self.input_params.get("file_name", "input.wav")}"

        # Set up microphone input
        if method == "microphone":
            p = pyaudio.PyAudio()
            logger.info("+----- INPUT DEVICES INFO -----")
            # https://stackoverflow.com/a/39677871 modified for logger.info
            info = p.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            selected = self.input_params.get("input_device_index")
            for i in range(0, numdevices):
                if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:  # is input device
                    device_info = p.get_device_info_by_host_api_device_index(0, i)
                    logger.info(f"| {">" if i == selected else " "} Input Device id {i}: {"(SELECTED)" if i == selected else ""}")
                    logger.info(f"|     name: {device_info.get('name')}")
                    logger.info(f"|     sample rate: {device_info.get('defaultSampleRate')}")
            logger.info("|")
            logger.info("| (config.yaml -> input -> input_device_index)")
            logger.info("+------------------------------")
            # Set up microphone data stream
            # Based on https://people.csail.mit.edu/hubert/pyaudio/#record-example
            microphone_stream = p.open(format=pyaudio.get_format_from_width(self.pyaudio_params["sample_width_bytes"]),
                channels=self.pyaudio_params["channels"],
                rate=self.pyaudio_params["rate"],
                input=True,
                frames_per_buffer=self.pyaudio_params["chunk_size"],
                input_device_index=self.input_params.get("input_device_index"))

        # Set up wave file input (no FFmpeg)
        elif method == "file":
            if not self.use_ffmpeg:
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

        # FFmpeg
        self.ffmpeg_base = self.build_ffmpeg_base()

        # Debug
        if self.debug_write_file:
            output_file_path = self.input_params.get("debug_out_file_path", "media/output/sender_output.wav")
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

        # Set up performance logging
        if self.benchmark_on:
            # self.benchmark_logger.write_headers(["Sequence number", "Chunk read", "Chunk processed", "Chunk transmitted"])
            logger.info(f"Set up performance logging into file '{self.benchmark_logger.get_file_name()}'")

        # Finish set up
        logger.info("Sender setup complete!")


    # === KEY EXCHANGE === #
        logger.info(f"Waiting {self.socket_params["sender_delay_ms"]/1000} seconds to allow for receiver to bind... (config.yaml -> sockets -> sender_delay_ms)")
        time.sleep(self.socket_params["sender_delay_ms"]/1000)
        if self.use_plugin:
            self.plugin.sender_key_exchange(sockfd)

    # === TRANSMIT === #
        transmission_start = time.perf_counter()
        # Stream microphone input to receiver
        if method == "microphone":
            # Inform user that transmission will start shortly
            logger.info("Microphone transmission will begin after the following countdown. Press Ctrl+C to stop transmitting.")
            for i in range(5, 0, -1):
                logger.info(f"{i}...")
                time.sleep(1)
            logger.info("Sending audio. Press Ctrl+C to stop")
            # Transmit chunks
            chunk_start = time.perf_counter()
            while True:
                try:
                    # Read chunk from microphone stream...
                    chunk = microphone_stream.read(self.pyaudio_params["chunk_size"], exception_on_overflow=False)  # TODO: OSError: [Errno -9981] Input overflowed

                    # ...Log timestamp...
                    if self.benchmark_on:
                        self.benchmark_logger.new_line(int.from_bytes(self.chunks_sent))
                        self.benchmark_logger.save_timestamp(time.perf_counter())

                    # ...Write to debug output...
                    if self.debug_write_file:
                        debug_wf.writeframes(chunk)

                    # ...Process...
                    chunk = self.process_chunk_for_sending(chunk)

                    # ...And transmit to receiver
                    self.send_stream_chunk_to_host(chunk, sockfd)

                    # Log final sender timestamp
                    if self.benchmark_on:
                        self.benchmark_logger.save_timestamp(time.perf_counter())
                        self.benchmark_logger.write_line()
                    
                    logger.info(f"Sent chunk {int.from_bytes(self.chunks_sent)} [{len(chunk)}B]")
                    self.increment_chunks_sent_mod()

                    chunk_end = time.perf_counter()
                    processing_time = chunk_end - chunk_start
                    if processing_time > self.ideal_chunk_time:
                        logger.warning(f"Chunk exceeded real-time processing time window!  Time: {processing_time}s, Target: {self.ideal_chunk_time}s")
                    else:
                        logger.info(f"Chunk processing time OK! ({processing_time}s, should be under or equal {self.ideal_chunk_time}s)")
                    chunk_start = chunk_end
                except KeyboardInterrupt:  # TODO: Doesn't work with compose attached, change to different method
                    logger.info("Ctrl+C detected, stopping transmission...")
                    break
        
        # Stream file contents to receiver
        elif method == "file":
            logger.info(f"Sending contents of {input_file_path} to {self.socket_params["receiver_host"]}...")
            if self.use_ffmpeg:
                logger.info(f"Using FFmpeg...")
                self.send_file_ffmpeg(sockfd)

            # Use proprietary file input        
            else:
                logger.info(f"Using CipherCaller proprietary implementation (not recommended!)...")
                self.send_file_proprietary(sockfd, wf, debug_wf)
        
        logger.info(f"Sending EOF")
        self.send_eof(sockfd)
        # Notify user about ending transmission
        logger.info(f"Transmission finished! Duration: {time.perf_counter() - transmission_start} seconds")

    # === CLEAN UP === #
        if self.use_plugin:  # Plugin
            self.plugin.sender_cleanup()
        if method == "microphone":  
            # PyAudio
            microphone_stream.close()
            p.terminate()
        elif method == "file" and not self.use_ffmpeg:  # Wave
            wf.close()
        sockfd.close()  # Sockets
        return


    def run_key_exchange_benchmark(self, config):
    # === SET UP === #
        # Set up sender socket
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Benchmarking
        if not self.benchmark_on:
            logger.warning("Trying to run key exchange benchmark without saving timestamps!")
            sys.exit()