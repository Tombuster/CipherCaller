import logging  # logs
import os  # checking files
import subprocess  # FFmpeg pipe
import time  # datetime in file names
import csv  # timestamp file consolidation
import json  # machine-readable report
from typing import Any
from math import sqrt
from visqol import VisqolApi
from scipy.io import wavfile
from pesqc2 import pesq

logger = logging.getLogger(__name__)

class Analyzer:
    def __init__(self, config:dict) -> None:
        self.config = config
        self.reference_file_path = f"media/input/{config["input"].get("file_name", "input.wav")}"
        self.distorted_file_path = f"media/output/{config["output"].get("file_name", "output.wav")}"
        self.analyzer_params = config.get("analyzer", {})
    
    def run_audio_metrics(self) -> dict:
        # PSNR
        # TODO: do away with sdr - not used as quality metric
        filter_complex = (
            "[0:a]asplit=2[ref1][ref2];"
            "[1:a]asplit=2[dist1][dist2];"
            "[ref1][dist1]apsnr[apsnr];"
            "[ref2][dist2]asdr[asdr]"
        )
        maps = ["-map", "[apsnr]", "-map", "[asdr]"]
        cmd = [
            "ffmpeg", "-hide_banner",
            "-i", self.reference_file_path,
            "-i", self.distorted_file_path,
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
        
        # ViSQOL
        visqol_api = VisqolApi()
        visqol_api.create(mode=self.analyzer_params.get("visqol_mode", "audio"))
        visqol_result = visqol_api.measure(self.reference_file_path, self.distorted_file_path)
        results["visqol mos-lqo"] = visqol_result.moslqo

        # PESQ
        # TODO: what to do for sampling rates other than 16000 (wideband) and 8000 (narrowband)
        if self.analyzer_params.get("run_pesq", False):
            rate, ref = wavfile.read("./audio/speech.wav")
            rate, deg = wavfile.read("./audio/speech_bab_0dB.wav")
            if rate == 16000:
                results["pesq"] = {'wb': pesq(rate, ref, deg, 'wb'), 'nb': pesq(rate, ref, deg, 'nb')}
            elif rate == 8000:  # 8kHz only compatible with narrowband mode
                results["pesq"] = {'wb': None, 'nb': pesq(rate, ref, deg, 'nb')}
            else:
                logger.warning("Trying to run PESQ on incompatible sampling rate file, skipping...")
                results["pesq"] = {'wb': None, 'nb': None}
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

    def write_all_timestamps(self, sender_file_reader:csv.DictReader, receiver_file_reader:csv.DictReader, timestamp_file_writer:csv.DictWriter) -> list[list[str | Any]]:
        '''Consolidates all timestamps in *sender_file_reader* and *receiver_file_reader* to *timestamp_file_writer* and returns an array containing the consolidated timestamps'''
        sender_dict = {row[0]: [row[1], row[2], row[3]] for row in sender_file_reader}
        receiver_dict = {row[0]: [row[1], row[2], row[3]] for row in receiver_file_reader}
        sequence_numbers = set(sender_dict.keys())
        for key in receiver_dict.keys():
            sequence_numbers.add(key)
        sequence_numbers = sorted(sequence_numbers, key=int)

        timestamps = []

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
            timestamps.append(row)
        return timestamps

    def remove_temp_files(self) -> None:
        logger.info("Removing temporary files...")
        for file_name in os.listdir("measurements/.tmp"):
            os.remove(f"measurements/.tmp/{file_name}")

    def calculate_transmission_stats(self, timestamps) -> dict[str | Any]:
        '''Calculates transmission time statistics and returns dict for writing into json_report'''
        logger.info("Calculating transmission metrics...")
        ans = {}

        # Total time:
        ans['time'] = {}
        ans['processing'] = {}
        i = 1
        while timestamps[-i][6] == '':
            i += 1
        ans['time']['total'] = float(timestamps[-i][6]) - float(timestamps[0][3])

        # Chunk average and maximum:
        received_count = 0
        transmission_time_sum = 0
        transmission_time_maximum = 0
        transmission_time_maximum_index = 0
        transmission_time_minimum = float('inf')
        transmission_time_minimum_index = 0
        processing_time_sum = 0
        processing_time_maximum = 0
        processing_time_maximum_index = 0
        processing_time_minimum = float('inf')
        processing_time_minimum_index = 0

        for row in timestamps:
            if row[4] != '':
                received_count += 1
                transmission_time = float(row[4]) - float(row[3])
                transmission_time_sum += transmission_time
                if transmission_time > transmission_time_maximum:
                    transmission_time_maximum = transmission_time
                    transmission_time_maximum_index = int(row[0])
                elif transmission_time < transmission_time_minimum:
                    transmission_time_minimum = transmission_time
                    transmission_time_minimum_index = int(row[0])
                processing_time = float(row[2]) - float(row[1]) + float(row[5]) - float(row[4])
                processing_time_sum += processing_time
                if processing_time > processing_time_maximum:
                    processing_time_maximum = processing_time
                    processing_time_maximum_index = int(row[0])
                elif processing_time < processing_time_minimum:
                    processing_time_minimum = processing_time
                    processing_time_minimum_index = int(row[0])
        transmission_time_average = transmission_time_sum / received_count
        processing_time_average = processing_time_sum / received_count
        ans['time']['sum'] = transmission_time_sum
        ans['time']['minimum'] = {'value': transmission_time_minimum, 'index': transmission_time_minimum_index}
        ans['time']['average'] = transmission_time_average
        ans['time']['maximum'] = {'value': transmission_time_maximum, 'index': transmission_time_maximum_index}
        ans['processing']['sum'] = processing_time_sum
        ans['processing']['minimum'] = {'value': processing_time_minimum, 'index': processing_time_minimum_index}
        ans['processing']['average'] = processing_time_average
        ans['processing']['maximum'] = {'value': processing_time_maximum, 'index': processing_time_maximum_index}

        # Standard deviation:
        transmission_time_std_dev_sum = 0
        processing_time_std_dev_sum = 0
        for row in timestamps:
            if row[4] != '':
                transmission_time_std_dev_sum += pow(float(row[4]) - float(row[3]) - transmission_time_average, 2)
                processing_time_std_dev_sum += pow(float(row[2]) - float(row[1]) + float(row[5]) - float(row[4]) - processing_time_average, 2)
        transmission_time_std_dev = sqrt(transmission_time_std_dev_sum / received_count)
        processing_time_std_dev = sqrt(processing_time_std_dev_sum / received_count)
        ans['time']['standard deviation'] = transmission_time_std_dev
        ans['processing']['standard deviation'] = processing_time_std_dev

        ans['chunks sent'] = len(timestamps)
        ans['chunks received'] = received_count
        ans['packet loss'] = 1 - received_count / len(timestamps)
        return ans

    def calculate_cryptography_stats(self, timestamps) -> dict[str | Any]:
        '''Calculates cryptography time statistics and returns dict for writing into json_report'''
        logger.info("Calculating cryptography metrics...")
        ans = {}

        received_count = 0
        sum_encrypt = 0
        sum_decrypt = 0
        sum_processing = 0
        minimum_encrypt = float('inf')
        minimum_decrypt = float('inf')
        minimum_processing = float('inf')
        maximum_encrypt = 0
        maximum_decrypt = 0
        maximum_processing = 0

        minimum_encrypt_index = 0
        minimum_decrypt_index = 0
        minimum_processing_index = 0
        maximum_encrypt_index = 0
        maximum_decrypt_index = 0
        maximum_processing_index = 0

        for row in timestamps:

            if row[4] != '':
                received_count += 1
                encrypt_time = float(row[2]) - float(row[1])
                decrypt_time = float(row[5]) - float(row[4])
                processing_time = encrypt_time + decrypt_time

                sum_encrypt += encrypt_time
                sum_decrypt += decrypt_time
                sum_processing += processing_time

                if encrypt_time > maximum_encrypt:
                    maximum_encrypt = encrypt_time
                    maximum_encrypt_index = int(row[0])
                elif encrypt_time < minimum_encrypt:
                    minimum_encrypt = encrypt_time
                    minimum_encrypt_index = int(row[0])

                if decrypt_time > maximum_decrypt:
                    maximum_decrypt = decrypt_time
                    maximum_decrypt_index = int(row[0])
                elif decrypt_time < minimum_decrypt:
                    minimum_decrypt = decrypt_time
                    minimum_decrypt_index = int(row[0])

                if processing_time > maximum_processing:
                    maximum_processing = processing_time
                    maximum_processing_index = int(row[0])
                elif processing_time < minimum_processing:
                    minimum_processing = processing_time
                    minimum_processing_index = int(row[0])

        average_encrypt = sum_encrypt / received_count
        average_decrypt = sum_decrypt / received_count
        average_processing = sum_processing / received_count

        # Standard deviation:
        encrypt_std_dev_sum = 0
        decrypt_std_dev_sum = 0
        processing_std_dev_sum = 0
        for row in timestamps:
            if row[4] != '':
                encrypt_std_dev_sum += pow(float(row[2]) - float(row[1]) - average_encrypt, 2)
                decrypt_std_dev_sum += pow(float(row[5]) - float(row[4]) - average_decrypt, 2)
                processing_std_dev_sum += pow(float(row[5]) - float(row[4]) + float(row[2]) - float(row[1]) - average_processing, 2)

        std_dev_encrypt = sqrt(encrypt_std_dev_sum / received_count)
        std_dev_decrypt = sqrt(decrypt_std_dev_sum / received_count)
        std_dev_processing = sqrt(processing_std_dev_sum / received_count)

        ans['encryption'] = {
            'minimum': {'value': minimum_encrypt, 'index': minimum_encrypt_index},
            'average': average_encrypt,
            'maximum': {'value': maximum_encrypt, 'index': maximum_encrypt_index},
            'standard deviation': std_dev_encrypt
        }
        ans['decryption'] = {
            'minimum': {'value': minimum_decrypt, 'index': minimum_decrypt_index},
            'average': average_decrypt,
            'maximum': {'value': maximum_decrypt, 'index': maximum_decrypt_index},
            'standard deviation': std_dev_decrypt
        }
        ans['processing'] = {
            'minimum': {'value': minimum_processing, 'index': minimum_processing_index},
            'average': average_processing,
            'maximum': {'value': maximum_processing, 'index': maximum_processing_index},
            'standard deviation': std_dev_processing
        }
        return ans

    def get_audio_file_info(self, file_path:str) -> dict[str | Any]:
        '''Fetches audio file information and returns it as dict for writing into json_report'''
        ans = {}
        
        cmd = [
            'ffprobe', '-hide_banner',
            '-v', 'error',
            '-show_streams',
            '-show_format',
            '-output_format', 'json=c=1',
            file_path
        ]
        attributes = subprocess.run(cmd, capture_output=True, text=True)
        attributes = json.loads(attributes.stdout)
        # print(attributes)
        ans['name'] = attributes['format']['filename']
        ans['size'] = attributes['format']['size']
        ans['duration'] = attributes['format']['duration']
        ans['channels'] = attributes['format']['nb_streams']
        ans['codec name'] = attributes['streams'][0]['codec_name']
        ans['codec long name'] = attributes['streams'][0]['codec_long_name']
        ans['sampling rate'] = attributes['streams'][0]['sample_rate']
        ans['sample format'] = attributes['streams'][0]['sample_fmt']
        ans['sample size'] = attributes['streams'][0]['bits_per_sample']
        ans['bit rate'] = attributes['format']['bit_rate']
        return ans

    def run_analyzer(self) -> None:
        if not os.path.exists(self.distorted_file_path):
            logger.error("Distorted file not found: %s", self.distorted_file_path)
            return {}

        self.use_plugin = self.config.get("plugin", {}).get("use_plugin")

    
        # Open files
        logger.info("Creating files...")
        reference_timestamp = time.localtime()
        file_name_timestamp = time.strftime("%d_%m_%y-%H_%M", reference_timestamp)
        plugin_name = self.config.get("plugin", {}).get("name") if self.use_plugin else "no_plugin"
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

    
        # Consolidate measurements
        logger.info("Consolidating measurements...")
        sender_file = open("measurements/.tmp/sender.csv", "r")
        receiver_file = open("measurements/.tmp/receiver.csv", "r")
    
        sender_file_reader = csv.reader(sender_file)
        receiver_file_reader = csv.reader(receiver_file)
        timestamp_file_writer = csv.writer(timestamp_file)
    
        timestamp_file_writer.writerow(["Sequence_number", "Sender_chunk_read", "Sender_chunk_processed", "Sender_chunk_transmitted", "Receiver_chunk_received", "Receiver_chunk_processed", "Receiver_chunk_written"])
        timestamps = self.write_all_timestamps(sender_file_reader, receiver_file_reader, timestamp_file_writer)
    
        sender_file.close()
        receiver_file.close()

    
        # Calculate transmission metrics
        json_report = {
            'input': {
                },
            'output': {
                },
            'transmission': {
            },
            'cryptography' : {
                'use plugin': self.use_plugin
            }
        }

        json_report['transmission'] = self.calculate_transmission_stats(timestamps)
        json_report['cryptography'] = self.calculate_cryptography_stats(timestamps)

        # Calculate audio metrics
        logger.info("Calculating audio metrics...")
        json_report['audio'] = self.run_audio_metrics()

        # Get input and output file statistics
        logger.info("Fetching transmission input and output file information...")
        input_params = self.config.get('input', {})
        output_params = self.config.get('output', {})
        json_report['input'] = self.get_audio_file_info(f"media/input/{input_params.get("file_name", "input.wav")}")
        json_report['output'] = self.get_audio_file_info(f"media/output/{output_params.get("file_name", "output.wav")}")
    
        # Generate reports
        # TODO: fill out the text and JSON reports
        logger.info("Generating reports...")
        report_text_file.write(
            f'''===== CipherCaller Measurement Report =====
Date and time: {time.strftime("%d/%m/%Y %H:%M", reference_timestamp)}
Plugin: {plugin_name if self.use_plugin else "no plugin used"}

= Input file stats =
Name: {json_report['input']['name']}
Size: {json_report['input']['size']}
Duration: {json_report['input']['duration']}
Channels: {json_report['input']['channels']}
Sampling rate: {json_report['input']['sampling rate']}
Codec: {json_report['input']['codec name']} ({json_report['input']['codec long name']})
Sample format: {json_report['input']['sample format']}
Sample size: {json_report['input']['sample size']} bits
Bit rate: {json_report['input']['bit rate']} bits per second

= Output file stats =
Name: {json_report['output']['name']}
Size: {json_report['output']['size']}
Duration: {json_report['output']['duration']}
Channels: {json_report['output']['channels']}
Sampling rate: {json_report['output']['sampling rate']}
Codec: {json_report['output']['codec name']} ({json_report['output']['codec long name']})
Sample format: {json_report['output']['sample format']}
Sample size: {json_report['output']['sample size']} bits
Bit rate: {json_report['output']['bit rate']} bits per second

= Transmission stats =
Transmission time*: 
    Total: {json_report['transmission']['time']['total']} seconds (First byte sent to last byte received. If the last packet is lost, this is calculated to the final received packet.)
    Sum: {json_report['transmission']['time']['sum']} seconds (Sum time between sending and receiving each packet)
    Minimum: {json_report['transmission']['time']['minimum']['value']} seconds (chunk {json_report['transmission']['time']['minimum']['index']}) (equals minimum latency)
    Average: {json_report['transmission']['time']['average']} seconds (per chunk) (equals average latency)
    Maximum: {json_report['transmission']['time']['maximum']['value']} seconds (chunk {json_report['transmission']['time']['maximum']['index']}) (equals maximum latency)
    Std. Deviation: {json_report['transmission']['time']['standard deviation']}
Chunks sent: {json_report['transmission']['chunks sent']}
Chunks received: {json_report['transmission']['chunks received']}
Packet loss: {json_report['transmission']['packet loss']*100}%
Chunk processing time (end of read -> sent + received -> start of write):
    Target:  (Maximum time available to keep up with real-time playback)
    Sum: {json_report['transmission']['processing']['sum']} seconds
    Minimum: {json_report['transmission']['processing']['minimum']['value']} seconds (chunk {json_report['transmission']['processing']['minimum']['index']})
    Average: {json_report['transmission']['processing']['average']} seconds (per chunk)
    Maximum: {json_report['transmission']['processing']['maximum']['value']} seconds (chunk {json_report['transmission']['processing']['maximum']['index']})
    Std. Deviation: {json_report['transmission']['processing']['standard deviation']}

* Transmission time value only valid between two containers running on one host. Values calculated using successfully received packets only.
{'' if not self.use_plugin else f'''
= Cryptography stats =
Encryption time:
    Minimum: {json_report['cryptography']['encryption']['minimum']['value']} (chunk {json_report['cryptography']['encryption']['minimum']['index']})
    Average: {json_report['cryptography']['encryption']['average']}
    Maximum: {json_report['cryptography']['encryption']['maximum']['value']} (chunk {json_report['cryptography']['encryption']['maximum']['index']})
    Std. Deviation: {json_report['cryptography']['encryption']['standard deviation']}
Decryption time:
    Minimum: {json_report['cryptography']['decryption']['minimum']['value']} (chunk {json_report['cryptography']['decryption']['minimum']['index']})
    Average: {json_report['cryptography']['decryption']['average']}
    Maximum: {json_report['cryptography']['decryption']['maximum']['value']} (chunk {json_report['cryptography']['decryption']['maximum']['index']})
    Std. Deviation: {json_report['cryptography']['decryption']['standard deviation']}
Cryptography time overhead:
    Minimum per chunk: {json_report['cryptography']['processing']['minimum']['value']} (chunk {json_report['cryptography']['processing']['minimum']['index']})
    Average per chunk: {json_report['cryptography']['processing']['average']}
    Maximum per chunk: {json_report['cryptography']['processing']['maximum']['value']} (chunk {json_report['cryptography']['processing']['maximum']['index']})
    Std. Deviation: {json_report['cryptography']['processing']['standard deviation']}
'''}
= Audio metrics =
Peak Signal-to-Noise Ratio (PSNR) (channel average): {json_report['audio']['psnr']}dB (higher is better; >50 dB is generally indistinguishable from source. Interpretation varries across codecs, compression, etc.)
ViSQOL: {json_report['audio']['visqol mos-lqo']} (1.0 - 5.0, higher is better)
{'' if not self.analyzer_params.get("run_pesq", False) else
 f'''PESQ*:
    Wideband: {'not calculated' if json_report['audio']['pesq']['wb'] is None else json_report['audio']['pesq']['wb']} (1.0 - 5.0, higher is better)
    Narrowband: {'not calculated' if json_report['audio']['pesq']['nb'] is None else json_report['audio']['pesq']['nb']} (1.0 - 5.0, higher is better)

* using implementation if the 2018 ITU Corrigendum 2. Scores not comparable with PESQ implementations which do not use the Corrigendum! Although it is obsolete, it is free to use and still utilized in many papers.'''}''')

        report_json_file.write(json.dumps(json_report))

        # Remove temporary files
        self.remove_temp_files()
        
        # Close files
        logger.info("Closing files...")
        report_text_file.close()
        report_json_file.close()
        timestamp_file.close()

        logger.info("Done!")
        return
