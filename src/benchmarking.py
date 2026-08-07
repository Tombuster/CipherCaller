import csv
import logging

logger = logging.getLogger(__name__)

class TimestampLogger:
    def __init__(self, config: dict, suffix: str):
        # File stuff
        self.suffix = suffix
        self.file_name = f"{config.get("plugin", {}).get("name") if config.get("plugin", {}).get("use_plugin") else "no_plugin"}_{self.suffix}.csv"
        self.file_path = f"./measurements/{self.file_name}"
        # Functionality stuff
        self.current_line = []

        # TODO: file numbering for unique names
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
        logger.info(f"Written line to '{self.file_name}'")