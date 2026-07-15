from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config.yaml"


with open(CONFIG_PATH, encoding="utf-8") as file:
    CONFIG = yaml.safe_load(file)