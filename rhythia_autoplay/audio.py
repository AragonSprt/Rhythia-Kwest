
#  AUDIO LOOPBACK SYNC (WASAPI, Windows)
#  Detects song start by monitoring system audio via a loopback device.
#  sounddevice is optional - all public symbols degrade if absent.


import threading
import time

import numpy as np

from .constants import DIM, GREEN, YELLOW, c

# Optional dependency - feature degrades to countdown if missing.
try:
    import sounddevice as sd
    AUDIO_SYNC_AVAILABLE = True
except ImportError:
    AUDIO_SYNC_AVAILABLE = False

# Device name fragments that identify a loopback/virtual audio input.
# Add more entries here if you want to use a different virtual cable product.
_LOOPBACK_HINTS = ("loopback", "cable output", "stereo mix", "wave out mix")


def find_loopback_device() -> int | None:
    """
    Search for a WASAPI input device that mirrors system audio output.
    Matches by checking if any hint string appears in the lowercase device name.
    Returns the sounddevice device index, or None if not found.
    """
    if not AUDIO_SYNC_AVAILABLE:
        return None
    try:
        hostapis = sd.query_hostapis()
        wasapi_idx = next(
            (i for i, api in enumerate(hostapis) if "wasapi" in api["name"].lower()),
            None,
        )
        if wasapi_idx is None:
            return None

        for i, dev in enumerate(sd.query_devices()):
            if dev["hostapi"] != wasapi_idx:
                continue
            if dev["max_input_channels"] < 1:
                continue
            name_lower = dev["name"].lower()
            if any(hint in name_lower for hint in _LOOPBACK_HINTS):
                return i
    except Exception:
        pass
    return None


def wait_for_audio(stop_event: threading.Event, cfg: dict) -> float | None:
    """
    Open a WASAPI loopback stream and block until audio RMS exceeds the
    configured threshold (or the timeout / stop_event fires).

    Returns perf_counter timestamp at the moment of detection, or None.
    """
    device_idx = find_loopback_device()
    if device_idx is None:
        return None

    threshold = cfg.get("audio_threshold", 0.01)
    timeout   = cfg.get("audio_timeout",   60)

    # Query the device's native sample rate instead of assuming 44 100 Hz.
    device_info = sd.query_devices(device_idx)
    samplerate  = int(device_info["default_samplerate"])

    detected_at    = [None]
    detected_event = threading.Event()

    def _callback(indata, frames, time_info, status):
        if detected_event.is_set() or stop_event.is_set():
            raise sd.CallbackStop()
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        if rms > threshold:
            detected_at[0] = time.perf_counter()
            detected_event.set()
            raise sd.CallbackStop()

    try:
        with sd.InputStream(
            device=device_idx,
            channels=1,
            samplerate=samplerate,
            blocksize=512,           # ~11 ms chunks - keeps latency low
            callback=_callback,
        ):
            print(c(f"  [AUDIO] Listening on '{device_info['name']}' @ {samplerate} Hz...", DIM))
            print(c("  Press F3 to abort.", DIM))
            detected_event.wait(timeout=timeout)
    except Exception as e:
        print(c(f"  [AUDIO] Stream error: {e}", YELLOW))
        return None

    return detected_at[0]
