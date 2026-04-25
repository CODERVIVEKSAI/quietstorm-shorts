"""Channel config loader. Every generator reads through this so renaming the
channel is a one-line edit in data/channel.yml."""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ASSETS_DIR = REPO_ROOT / "assets"
OUTPUT_DIR = REPO_ROOT / "output"


def load_channel():
    with open(DATA_DIR / "channel.yml") as f:
        return yaml.safe_load(f)


def load_company():
    return (DATA_DIR / "company.md").read_text()


def voice_for(format_name: str) -> str:
    cfg = load_channel()
    return cfg.get("voices", {}).get(format_name, cfg["default_voice"])


def rate_for(format_name: str) -> str:
    """Per-format speech rate, e.g. '-7%' for slower. Falls back to '+0%'."""
    cfg = load_channel()
    return cfg.get("rates", {}).get(format_name, "+0%")


def video_dims():
    cfg = load_channel()
    v = cfg["video"]
    return v["width"], v["height"], v["fps"], v["max_duration_seconds"]
