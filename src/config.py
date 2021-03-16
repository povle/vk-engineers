import logging.config
from pathlib import Path
import yaml

logging_config_path = Path(__file__).parent / '../config/logger.conf'
logging.config.fileConfig(logging_config_path)

config_path = Path(__file__).parent / '../config/config.yaml'
with config_path.open() as f:
    config = yaml.safe_load(f)
