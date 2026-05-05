
#  CONFIG
#  Manages the persistent JSON configuration file.


import json
import os

from .constants import c, DIM

CONFIG_FILE = "../utils/rhythia_config.json"

DEFAULT_CONFIG: dict = {
    # 9-point calibration: cell_centers[row][col] = [px_x, px_y]
    "cell_centers": [],

    # Legacy 2-point fallback (used if cell_centers is empty).
    "grid_left":   660,
    "grid_top":    140,
    "grid_width":  600,
    "grid_height": 600,

    # Global timing offset
    # Use this to compensate for audio loopback latency or system input lag.
    "offset_ms": 0,

    # Audio detection sensitivity: RMS amplitude that counts as "song started".
    # Lower = more sensitive (may false-trigger on UI sounds).
    # Higher = less sensitive (may miss a quiet intro).
    "audio_threshold": 0.01,

    # Seconds to wait for audio before falling back to the countdown.
    "audio_timeout": 60,

    # Fallback countdown (seconds) used when audio sync is unavailable/skipped.
    "countdown": 5,

    # Mouse move duration in seconds. 0 = instant (best for accuracy).
    "move_duration": 0.0,

    # Hotkeys
    "quit_key":  "f3",
    "pause_key": "escape",
}


def load_config() -> dict:
    """
    Load the config from *CONFIG_FILE*, merging any missing keys from
    DEFAULT_CONFIG.  Returns DEFAULT_CONFIG unchanged if the file is absent
    or unreadable.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """Persist *cfg* to *CONFIG_FILE*, creating parent directories as needed."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(c(f"  Config saved → {CONFIG_FILE}", DIM))
