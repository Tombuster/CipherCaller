import os
import sys
import yaml
import logging
from time import sleep


def load_config(path_to_config_file: str = "config.yaml") -> dict:
    return yaml.safe_load(open(path_to_config_file))

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    )


def main() -> None:
    sleep(2)
    # Setup
    config = load_config()
    setup_logging(config.get("logging", {}).get("level", "INFO"))
    logger = logging.getLogger(__name__)
    # ROLE environment variable takes precedence over config
    role = os.environ.get("CIPHERCALLER-ROLE", config.get("role", "sender")).lower()
    logger.info(f"Setting up {role}...")

    # Running code according to config...
    # Route for key exchange benchmark
    if config.get("ciphercaller", None) is not None:
        if config["ciphercaller"].get("what_to_test", "transmission") == "key_exchange":
            if role == "sender":
                Sender(config).run_key_exchange_benchmark()
            elif role == "receiver":
                Receiver(config).run_key_exchange_benchmark()
            else:
                logger.error(f"Unsupported role: {role}!")
                sys.exit(1)
    else:
        # Running file for specified docker service based on role
        if role == "sender":
            from src.sender import Sender
            Sender(config).run_transmission()
        elif role == "receiver":
            from src.receiver import Receiver
            Receiver(config).run_transmission()
        elif role == "analyzer":
            from src.analyzer import Analyzer
            Analyzer(config).run_analyzer()
        else:
            logger.error(f"Unsupported role: {role}!")
            sys.exit(1)

if __name__ == "__main__":
    main()
