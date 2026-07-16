import os
import sys
import yaml
import logging
from time import sleep

from src.sender.sender import Sender
from src.receiver.receiver import Receiver


def load_config(path_to_config_file: str = "config.yaml") -> dict:
    return yaml.safe_load(open(path_to_config_file))

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    sleep(2)
    # Setup
    config = load_config()
    setup_logging(config.get("logging", {}).get("level", "INFO"))
    logger = logging.getLogger(__name__)
    # ROLE environment variable takes precedence over config
    role = os.environ.get("ROLE", config.get("role", "sender")).lower()
    logger.info(f"Setting up {role}...")

    # Running file for specified docker service based on role
    if role == "sender":
        Sender(config).run()
    elif role == "receiver":
        Receiver(config).run()
    else:
        logger.error(f"Unsupported role: {repr(role)}!")
        sys.exit(1)

if __name__ == "__main__":
    main()
