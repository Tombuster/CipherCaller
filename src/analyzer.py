import logging  # logs
import os  # checking files
import subprocess  # FFmpeg pipe
import time  # datetime in file names
import csv  # timestamp file consolidation
import json  # machine-readable report

logger = logging.getLogger(__name__)

class Analyzer:
    def __init__(self, config:dict) -> None:
        self.config = config
        self.reference = f"media/input/{config["input"].get("file_name", "input.wav")}"
        self.distorted = f"media/output/{config["output"].get("file_name", "output.wav")}"
    
    def run_audio_metrics(self) -> dict:
        filter_complex = (
            "[0:a]asplit=2[ref1][ref2];"
            "[1:a]asplit=2[dist1][dist2];"
            "[ref1][dist1]apsnr[apsnr];"
            "[ref2][dist2]asdr[asdr]"
        )
        maps = ["-map", "[apsnr]", "-map", "[asdr]"]
        cmd = [
            "ffmpeg", "-hide_banner",
            "-i", self.reference,
            "-i", self.distorted,
            "-filter_complex", filter_complex,
            *maps,
            "-f", "null", "-",
        ]
        stderr = self.run_ffmpeg_subprocess(cmd)

        results: dict = {"psnr": None, "sdr": None}
        psnr = []
        sdr = []
        if stderr is None:
            logger.error("_run_audio_metrics(): FFMPEG did not return results")
        for line in stderr.splitlines():
            if results["psnr"] is None and "PSNR" in line:
                psnr.append(float(line.split(":")[1].strip().split()[0]))
            if results["sdr"] is None and "SDR" in line:
                sdr.append(float(line.split(":")[1].strip().split()[0]))
        results["psnr"] = self.list_average(psnr)
        results["sdr"] = self.list_average(sdr)
        return results

    def run_ffmpeg_subprocess(self, cmd: list[str]) -> str | None:
        logger.debug("FFmpeg command: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg exited with code %d\n%s", result.returncode, result.stderr)
            return None
        return result.stderr

    def list_average(self, list: list[float]) -> float:
        x = 0.0
        [x := x+item for item in list]
        return x/len(list)

    def write_all_timestamps(self, sender_file_reader:csv.DictReader, receiver_file_reader:csv.DictReader, timestamp_file_writer:csv.DictWriter) -> None:
        sender_dict = {row[0]: [row[1], row[2], row[3]] for row in sender_file_reader}  # TODO: see if this includes headers  -YES, FIX!
        receiver_dict = {row[0]: [row[1], row[2], row[3]] for row in receiver_file_reader}  # TODO: see above
        sequence_numbers = set(sender_dict.keys())
        for key in receiver_dict.keys():
            sequence_numbers.add(key)
        sequence_numbers = sorted(sequence_numbers, key=int)  # TODO: sort sequence numbers

        for key in sequence_numbers:
            row = [key]
            tmp = sender_dict.get(key, None)
            if tmp is not None:
                for item in tmp:
                    row.append(item)
            else:
                for _ in range(3):
                    row.append('')
            tmp = receiver_dict.get(key, None)
            if tmp is not None:
                for item in tmp:
                    row.append(item)
            else:
                for _ in range(3):
                    row.append('')
            timestamp_file_writer.writerow(row)

    def remove_temp_files(self) -> None:
        logger.info("Removing temporary files...")
        for file_name in os.listdir("measurements/.tmp"):
            os.remove(f"measurements/.tmp/{file_name}")

    def run_analyzer(self) -> None:
        if not os.path.exists(self.distorted):
            logger.error("Distorted file not found: %s", self.distorted)
            return {}

        use_plugin = self.config.get("plugin", {}).get("use_plugin")

    
        # Open files
        logger.info("Creating files...")
        reference_timestamp = time.localtime()
        file_name_timestamp = time.strftime("%d_%m_%y-%H_%M", reference_timestamp)
        plugin_name = self.config.get("plugin", {}).get("name") if use_plugin else "no_plugin"
        file_directory_path = f"measurements/{file_name_timestamp}-{plugin_name}"

        suffix = ""
        i = 0
        while os.path.exists(file_directory_path+suffix):
            i = i + 1
            suffix = f"({i})"
        file_directory_path = file_directory_path+suffix
        os.mkdir(file_directory_path)
        report_text_file = open(f"{file_directory_path}/report.txt", "w")
        report_json_file = open(f"{file_directory_path}/report.json", "w")
        timestamp_file = open(f"{file_directory_path}/times.csv", "w",)


        # Analyze audio metrics
        logger.info("Calculating audio metrics...")
        ffmpeg_results = self.run_audio_metrics()

    
        # Consolidate measurements
        logger.info("Consolidating measurements...")
        sender_file = open("measurements/.tmp/sender.csv", "r")
        receiver_file = open("measurements/.tmp/receiver.csv", "r")
    
        sender_file_reader = csv.reader(sender_file)
        receiver_file_reader = csv.reader(receiver_file)
        timestamp_file_writer = csv.writer(timestamp_file)
    
        timestamp_file_writer.writerow(["Sequence_number", "Sender_chunk_read", "Sender_chunk_processed", "Sender_chunk_transmitted", "Receiver_chunk_received", "Receiver_chunk_processed", "Receiver_chunk_written"])
        self.write_all_timestamps(sender_file_reader, receiver_file_reader, timestamp_file_writer)
    
        sender_file.close()
        receiver_file.close()

    
        # Calculate packet loss and latencies
        logger.info("Calculating transmission metrics...")

    
        # Generate reports
        logger.info("Generating reports...")
        input_params = self.config["input"]
        report_text_file.write(  # TODO: fill out the text and JSON reports
            f'''===== CipherCaller Measurement Report =====
Date and time: {time.strftime("%d/%m/%Y %H:%M", reference_timestamp)}
Plugin: {plugin_name if use_plugin else "no plugin used"}

= Input file stats =
Name: {input_params.get("file_name", "input.wav")}
Size: {os.path.getsize(f"media/input/{self.input_params.get("file_name", "input.wav")}")}
Length: 
Sampling rate:
Channels:
Sample format (size): (B)
Codec:

= Transmission stats =
Total transmission time: seconds
Chunk size:
Chunks sent:
Chunks received:
Packet loss:
Chunk processing time (end of read -> sent + received -> start of write):
    Target:  (Maximum time available to keep up with real-time playback)
    Average: 
    Maximum: 
    Std. Deviation: 
Transmission time (latency)*:
    Average: 
    Maximum: 
    Std. Deviation: 
Time to last byte**:

* Transission time value only valid between two containers running on one host
** Time to last byte will vary with chunk sizes
{'' if not use_plugin else f'''
= Cryptography stats =
Encryption time:
    Average: 
    Maximum: 
    Std. Deviation: 
Decryption time:
    Average: 
    Maximum: 
    Std. Deviation: 
Cryptography time overhead:
    Average per chunk: 
    Maximum per chunk: 
    Sum: 
'''}
= Audio metrics =
Peak Signal-to-Noise Ratio (PSNR) (channel average): {ffmpeg_results["psnr"]}dB (higher is better; >50 dB is generally indistinguishable from source. Interpretation varries across codecs, compression, etc.)
Signal-to-Distortion Ratio (SDR):
''')

        # Remove temporary files
        self.remove_temp_files()
        
        # Close files
        logger.info("Closing files...")
        report_text_file.close()
        timestamp_file.close()

        logger.info("Done!")
        return
