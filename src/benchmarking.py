import csv

class TimestampLogger:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.current_row = []
        self.headers = ["sequence_number", ""]
        pass

    def write_headers(self) -> None:
        pass
    
    def write_timestamp(dict_writer: csv.DictWriter, sequence_number: int, timestamp_number: int) -> None:
        pass

    def close(self) -> None:
        # close files
        pass