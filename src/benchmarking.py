import csv
import logging
import os  # file management
# from pathlib import rmtree

logger = logging.getLogger(__name__)

class TimestampLogger:
    def __init__(self, config: dict, suffix: str, temporary: bool = True):
        # File stuff
        self.suffix = suffix
        self.file_name = f"{self.suffix}.csv"
        if not os.path.isdir("./measurements"):  # check if "measurements" exitst
            os.mkdir("./measurements")  # if not, create it
        if not os.path.isdir("./measurements/.tmp"):  # check if "measurements/.tmp" exitst
            os.mkdir("./measurements/.tmp")  # if not, create it
        self.file_path = f"./measurements/{".tmp/" if temporary else ""}{self.file_name}"
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
        # Functionality stuff
        self.current_line = []
        pass

    def get_file_name(self) -> str:
        return self.file_name

    def write_headers(self, headers: list[str]) -> None:
        with open(self.file_path, 'w') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
        logger.info(f"Written headers to '{self.file_name}'")

    def new_line(self, sequence_number: int) -> None:
        self.current_line = [sequence_number]
    
    def save_timestamp(self, timestamp_value: float | None) -> None:
        self.current_line.append(timestamp_value)

    def write_line(self) -> None:
        with open(self.file_path, 'a') as file:
            writer = csv.writer(file)
            writer.writerow(self.current_line)
        # logger.info(f"Written line to '{self.file_name}'")

    # def remove_temp_files(self) -> None:
    #     rmtree("./measurements/tmp")