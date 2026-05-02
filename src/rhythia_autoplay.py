import sys
import time
import json
import os
import threading
import argparse
import ctypes
from pathlib import Path


# --- Third-party ---
try:
    import pyautogui
    import keyboard
    import pydirectinput
    import pysspm_rhythia
    import numpy as np

    # Compatibility shim for pysspm-rhythia v2
    sys.modules["pysspm"] = pysspm_rhythia.pysspm
    from pysspm_rhythia import read_sspm

except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("  Run:  pip install -r requirements.txt")
    sys.exit(1)

# sounddevice is optional — audio sync degrades gracefully to countdown if absent
try:
    import sounddevice as sd
    AUDIO_SYNC_AVAILABLE = True
except ImportError:
    AUDIO_SYNC_AVAILABLE = False

pydirectinput.PAUSE    = 0.0
pydirectinput.FAILSAFE = False


# ═════════════════════════════════════════════════════════════════════════════
#  DPI AWARENESS  (must run before any coordinate is read or written)
# ═════════════════════════════════════════════════════════════════════════════

def set_dpi_aware():
    """
    Tell Windows that this process handles DPI scaling itself, so all Win32
    coordinate APIs (GetCursorPos, SetCursorPos, SendInput …) return and
    accept RAW PHYSICAL pixels instead of scaled logical pixels.

    Without this, at 150 % scaling every coordinate is off by ×1.5:
    pyautogui reads logical pixels during calibration, but pydirectinput
    sends physical pixels during playback → mouse lands in the wrong place.

    We try the modern per-monitor-v2 API first, then the legacy fallback.
    A re-calibration is required after applying this fix for the first time.
    """
    try:
        # Windows 8.1+  PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except AttributeError:
        pass
    try:
        # Windows Vista+ legacy fallback
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        pass  # non-Windows: no-op


# --- Constants ---
CONFIG_FILE = "../utils/rhythia_config.json"

DEFAULT_CONFIG = {
    # 9-point calibration: cell_centers[row][col] = [px_x, px_y]
    # Populated by the calibration wizard — empty means uncalibrated.
    "cell_centers": [],

    # Legacy 2-point fallback (used if cell_centers is empty)
    "grid_left":   660,
    "grid_top":    140,
    "grid_width":  600,
    "grid_height": 600,

    # Global timing offset in milliseconds.
    # Positive  → clicks fire later.
    # Negative  → clicks fire earlier.
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

# Human-readable labels for the 9 calibration points (row-major order).
# Indexed as CELL_LABELS[row][col] — matches cell_centers[row][col].
CELL_LABELS = [
    ["TOP-LEFT",    "TOP-CENTER",    "TOP-RIGHT"   ],
    ["MIDDLE-LEFT", "MIDDLE-CENTER", "MIDDLE-RIGHT"],
    ["BOTTOM-LEFT", "BOTTOM-CENTER", "BOTTOM-RIGHT"],
]

# Visual reference printed during calibration.
GRID_DIAGRAM = """
      col 0        col 1        col 2
    ┌────────────┬────────────┬────────────┐
row │  TOP-LEFT  │ TOP-CENTER │ TOP-RIGHT  │  ← y = 0
 0  │   (0, 0)   │   (1, 0)   │   (2, 0)   │
    ├────────────┼────────────┼────────────┤
row │  MID-LEFT  │ MID-CENTER │  MID-RIGHT │  ← y = 1
 1  │   (0, 1)   │   (1, 1)   │   (2, 1)   │
    ├────────────┼────────────┼────────────┤
row │  BOT-LEFT  │ BOT-CENTER │  BOT-RIGHT │  ← y = 2
 2  │   (0, 2)   │   (1, 2)   │   (2, 2)   │
    └────────────┴────────────┴────────────┘
"""


# --- Colour helpers ---
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def c(text, colour): return f"{colour}{text}{RESET}"


# ═════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(c(f"  Config saved → {CONFIG_FILE}", DIM))


# ═════════════════════════════════════════════════════════════════════════════
#  COORDINATE MAPPING
# ═════════════════════════════════════════════════════════════════════════════

def note_to_screen(x: float, y: float, cfg: dict) -> tuple[int, int]:
    """
    Convert an SSPM note coordinate (x, y) to screen pixel coordinates.

    If 9-point calibration data is present (cfg["cell_centers"]):
        - Integer notes (standard grid) → direct lookup in the 3×3 table.
        - Quantum float notes           → bilinear interpolation between the
                                          four surrounding calibrated centers.

    Falls back to the legacy 2-corner bounding-box formula otherwise.
    """
    centers = cfg.get("cell_centers", [])

    if not centers:
        # Legacy fallback
        cell_w = cfg["grid_width"]  / 3
        cell_h = cfg["grid_height"] / 3
        px = cfg["grid_left"] + (x + 0.5) * cell_w
        py = cfg["grid_top"]  + (y + 0.5) * cell_h
        return int(px), int(py)

    # Clamp to the valid [0, 2] range (handles minor quantum out-of-bounds)
    xc = max(0.0, min(2.0, float(x)))
    yc = max(0.0, min(2.0, float(y)))

    # Exact integer position → direct lookup
    if xc == int(xc) and yc == int(yc):
        pt = centers[int(yc)][int(xc)]
        return int(pt[0]), int(pt[1])

    # Quantum position → bilinear interpolation
    # x0/y0 are the lower-index corners; clamped so x1/y1 never exceed 2.
    x0 = min(int(xc), 1)
    y0 = min(int(yc), 1)
    x1, y1 = x0 + 1, y0 + 1

    tx = xc - x0   # fractional position within patch, x axis [0, 1]
    ty = yc - y0   # fractional position within patch, y axis [0, 1]

    c00 = centers[y0][x0]   # top-left of the local patch
    c10 = centers[y0][x1]   # top-right
    c01 = centers[y1][x0]   # bottom-left
    c11 = centers[y1][x1]   # bottom-right

    px = (c00[0] * (1 - tx) * (1 - ty)
        + c10[0] *      tx  * (1 - ty)
        + c01[0] * (1 - tx) *      ty
        + c11[0] *      tx  *      ty)

    py = (c00[1] * (1 - tx) * (1 - ty)
        + c10[1] *      tx  * (1 - ty)
        + c01[1] * (1 - tx) *      ty
        + c11[1] *      tx  *      ty)

    return int(px), int(py)


# ═════════════════════════════════════════════════════════════════════════════
#  9-POINT CALIBRATION
# ═════════════════════════════════════════════════════════════════════════════

def calibrate(cfg: dict) -> dict:
    def c(text, colour):
        return f"{colour}{text}{RESET}"

    print()
    print(c("  --- 9-Point Grid Calibration ---", BOLD))
    print("  Switch to the Rhythia window (keep this terminal visible on the side).")
    print("  For each of the 9 cells you will hover over its CENTER, then press ENTER.")
    print(GRID_DIAGRAM)

    def capture(label: str, col: int, row: int) -> list[int]:
        input(f"  [{row},{col}]  Hover over {c(label, YELLOW)} center and press ENTER...")
        pos = pyautogui.position()
        print(c(f"        → Captured: ({pos.x}, {pos.y})", DIM))
        return [pos.x, pos.y]

    # Build a 3×3 list: centers[row][col]
    centers = []
    for row in range(3):
        row_data = []
        for col in range(3):
            pt = capture(CELL_LABELS[row][col], col, row)
            row_data.append(pt)
        centers.append(row_data)

    cfg["cell_centers"] = centers

    # Derive legacy bounding box from the 9 points (used for the summary display)
    all_x = [centers[r][c][0] for r in range(3) for c in range(3)]
    all_y = [centers[r][c][1] for r in range(3) for c in range(3)]
    cfg["grid_left"]   = min(all_x)
    cfg["grid_top"]    = min(all_y)
    cfg["grid_width"]  = max(all_x) - min(all_x)
    cfg["grid_height"] = max(all_y) - min(all_y)

    print()
    print(c("  Calibration complete! Captured cell centres:", GREEN))
    for row in range(3):
        row_str = "    "
        for col in range(3):
            pt = centers[row][col]
            row_str += f"({pt[0]:4d},{pt[1]:4d})  "
        print(row_str)
    print()

    save_config(cfg)
    return cfg


# ═════════════════════════════════════════════════════════════════════════════
#  AUDIO LOOPBACK SYNC  (WASAPI, Windows)
# ═════════════════════════════════════════════════════════════════════════════

def find_loopback_device() -> int | None:
    """
    Search for a WASAPI loopback input device that mirrors system audio output.
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
            if dev["hostapi"] == wasapi_idx and dev["max_input_channels"] > 0:
                if "loopback" in dev["name"].lower():
                    return i
    except Exception:
        pass
    return None


def wait_for_audio(stop_event: threading.Event, cfg: dict) -> float | None:
    """
    Block until system audio is detected via WASAPI loopback, or until
    stop_event is set or the timeout expires.

    Returns time.perf_counter() at the exact moment audio was first detected,
    or None if detection failed / timed out.
    """
    device_idx = find_loopback_device()
    if device_idx is None:
        return None

    threshold = cfg.get("audio_threshold", 0.01)
    timeout   = cfg.get("audio_timeout",   60)

    detected_at    = [None]
    detected_event = threading.Event()

    def _callback(indata, frames, time_info, status):
        if detected_event.is_set() or stop_event.is_set():
            raise sd.CallbackStop()
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        if rms > threshold:
            # Capture the timestamp as close to detection as possible
            detected_at[0] = time.perf_counter()
            detected_event.set()
            raise sd.CallbackStop()

    try:
        with sd.InputStream(
            device=device_idx,
            channels=1,
            samplerate=44100,
            blocksize=512,       # ~11 ms chunks — keeps latency low
            callback=_callback,
        ):
            print(c("  [AUDIO] Listening for song start via WASAPI loopback...", DIM))
            print(c("  Press F3 to abort.", DIM))
            detected_event.wait(timeout=timeout)
    except Exception as e:
        print(c(f"  [AUDIO] Stream error: {e}", YELLOW))
        return None

    return detected_at[0]


# ═════════════════════════════════════════════════════════════════════════════
#  MAP LOADING
# ═════════════════════════════════════════════════════════════════════════════

DIFFICULTY_NAMES = {
    0: "N/A",
    1: "Easy",
    2: "Medium",
    3: "Hard",
    4: "Logic",
    5: "Tasukete",
}


def load_map(path: str) -> list:
    print(c(f"\n  Reading: {path}", DIM))
    try:
        sspm = read_sspm(path)
    except Exception as e:
        print(c(f"[ERROR] Failed to read SSPM: {e}", RED))
        sys.exit(1)

    notes       = sorted(sspm.notes, key=lambda n: n[2])
    diff_id     = sspm.difficulty.value if hasattr(sspm.difficulty, "value") else 0
    diff        = DIFFICULTY_NAMES.get(diff_id, "Unknown")
    dur_s       = sspm.last_ms / 1000
    quantum     = any(isinstance(x, float) and x != int(x) for x, y, ms in notes)
    mappers_str = ", ".join(sspm.mappers)
    pad         = lambda s: " " * max(0, 29 - len(s))

    print()
    print(c("  ╔═══════════════════════════════════════╗", CYAN))
    print(c("  ║  Map   : ", CYAN) + c(sspm.map_name, BOLD) + c(pad(sspm.map_name) + "║", CYAN))
    print(c("  ║  Mapper: ", CYAN) + mappers_str             + c(pad(mappers_str)   + "║", CYAN))
    print(c(f"  ║  Diff  : {diff:<29}║", CYAN))
    print(c(f"  ║  Notes : {len(notes):<29}║", CYAN))
    print(c(f"  ║  Length: {dur_s:.1f}s{'':<25}║", CYAN))
    print(c(f"  ║  Quantum: {'Yes' if quantum else 'No':<28}║", CYAN))
    print(c("  ╚═══════════════════════════════════════╝", CYAN))
    print()

    return notes


# ═════════════════════════════════════════════════════════════════════════════
#  AUTO-PLAYER
# ═════════════════════════════════════════════════════════════════════════════

class AutoPlayer:
    def __init__(self, notes: list, cfg: dict):
        self.notes          = notes
        self.cfg            = cfg
        self._stop          = threading.Event()
        self._pause         = threading.Event()
        self._paused_at     = 0.0
        self._pause_elapsed = 0.0

        keyboard.add_hotkey(cfg["quit_key"],  self._on_quit,  suppress=True)
        keyboard.add_hotkey(cfg["pause_key"], self._on_pause, suppress=True)

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE    = 0

    # ── Hotkeys ──────────────────────────────────────────────────────────────

    def _on_quit(self):
        print(c("\n  [F3] Emergency stop!", RED))
        self._stop.set()
        self._pause.clear()

    def _on_pause(self):
        if self._stop.is_set():
            return
        if self._pause.is_set():
            paused_for = time.perf_counter() - self._paused_at
            self._pause_elapsed += paused_for
            self._pause.clear()
            print(c("  [ESC] Resumed.", GREEN))
        else:
            self._paused_at = time.perf_counter()
            self._pause.set()
            print(c("  [ESC] Paused — press ESC again to resume.", YELLOW))

    # ── Precise timing ────────────────────────────────────────────────────────

    def _wait_until(self, target_perf: float) -> bool:
        """
        Sleep until target_perf (a perf_counter value), accounting for any
        time spent paused.  Returns False immediately if the user quit.
        """
        while True:
            if self._stop.is_set():
                return False
            if self._pause.is_set():
                time.sleep(0.01)
                continue
            remaining = (target_perf + self._pause_elapsed) - time.perf_counter()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.005))

    # ── Sync strategies ───────────────────────────────────────────────────────

    def _sync_audio(self) -> float | None:
        """
        Try to auto-detect song start via WASAPI loopback.
        Returns perf_counter at detection, or None (caller falls back to countdown).
        """
        if not AUDIO_SYNC_AVAILABLE:
            print(c("  [AUDIO] sounddevice not installed — falling back to countdown.", YELLOW))
            return None

        if find_loopback_device() is None:
            print(c("  [AUDIO] No WASAPI loopback device found — falling back to countdown.", YELLOW))
            print(c("  [TIP]   Enable 'Stereo Mix' in Sound settings, or install VB-Cable.", DIM))
            return None

        print(c(f"\n  Start the map in Rhythia whenever you are ready.", YELLOW))
        detected = wait_for_audio(self._stop, self.cfg)

        if self._stop.is_set():
            return None
        if detected is None:
            print(c("  [AUDIO] Timed out — falling back to countdown.", YELLOW))
            return None

        print(c("  [AUDIO] Song detected — syncing!", GREEN))
        return detected

    def _sync_countdown(self) -> float | None:
        """Classic countdown. Returns perf_counter at t=0, or None on quit."""
        countdown = self.cfg["countdown"]
        print(c(f"\n  Focus the Rhythia window now!", YELLOW))
        print(c(f"  Starting in {countdown}s  (F3 = quit, ESC = pause)\n", DIM))

        t0 = time.perf_counter()
        for i in range(countdown, 0, -1):
            print(c(f"  {i}...", BOLD), end="\r", flush=True)
            if not self._wait_until(t0 + (countdown - i + 1)):
                return None

        print(c("  GO!                  ", GREEN))
        return time.perf_counter()

    # ── Main playback loop ────────────────────────────────────────────────────

    def run(self, use_audio_sync: bool = True):
        offset_s = self.cfg["offset_ms"] / 1000.0

        # Determine t=0 (the moment the song begins)
        start = None
        if use_audio_sync:
            start = self._sync_audio()
        if start is None:
            if self._stop.is_set():
                return
            start = self._sync_countdown()
        if start is None or self._stop.is_set():
            return

        # Playback
        total  = len(self.notes)
        played = 0

        for x, y, ms in self.notes:
            if self._stop.is_set():
                break

            target_perf = start + (ms / 1000.0) + offset_s
            if not self._wait_until(target_perf):
                break

            px, py = note_to_screen(x, y, self.cfg)
            pydirectinput.moveTo(px, py, duration=self.cfg["move_duration"])
            pydirectinput.click()

            played += 1
            if played % 50 == 0 or played == total:
                pct = played / total * 100
                bar = ("█" * int(pct // 5)).ljust(20)
                print(c(f"  [{bar}] {pct:5.1f}%  ({played}/{total})", DIM),
                      end="\r", flush=True)

        keyboard.remove_all_hotkeys()
        print()
        if self._stop.is_set():
            print(c("\n  Stopped early.", YELLOW))
        else:
            print(c("\n  Map complete! ✓", GREEN))


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def main():
    # Must be the FIRST call — before pyautogui, pydirectinput, or any coordinate
    # read/write.  Forces the entire process into physical-pixel mode on Windows,
    # fixing the DPI scaling mismatch that causes the mouse to land in wrong places.
    set_dpi_aware()

    parser = argparse.ArgumentParser(
        description="Official Rhythia SSPM Auto-Player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("sspm", nargs="?", help="Path to the .sspm map file")
    parser.add_argument("-c", "--calibrate", action="store_true",
                        help="Re-run the 9-point grid calibration wizard")
    parser.add_argument("--no-audio-sync", action="store_true",
                        help="Skip WASAPI detection and use the countdown instead")
    parser.add_argument("--offset", type=int, default=None, metavar="MS",
                        help="Override timing offset in milliseconds (e.g. --offset -50)")
    parser.add_argument("--countdown", type=int, default=None, metavar="SEC",
                        help="Override fallback countdown duration in seconds")
    parser.add_argument("--threshold", type=float, default=None, metavar="RMS",
                        help="Override audio detection sensitivity (default 0.01)")
    args = parser.parse_args()

    # --- Banner ---
    print()
    print(c("  ██████╗ ██╗  ██╗██╗   ██╗████████╗██╗  ██╗██╗ █████╗ ", CYAN))
    print(c("  ██╔══██╗██║  ██║╚██╗ ██╔╝╚══██╔══╝██║  ██║██║██╔══██╗", CYAN))
    print(c("  ██████╔╝███████║ ╚████╔╝    ██║   ███████║██║███████║", CYAN))
    print(c("  ██╔══██╗██╔══██║  ╚██╔╝     ██║   ██╔══██║██║██╔══██║", CYAN))
    print(c("  ██║  ██║██║  ██║   ██║      ██║   ██║  ██║██║██║  ██║", CYAN))
    print(c("  ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝", CYAN))
    print(c("        ██╗  ██╗██╗    ██╗███████╗███████╗████████╗", CYAN))
    print(c("        ██║ ██╔╝██║    ██║██╔════╝██╔════╝╚══██╔══╝", CYAN))
    print(c("  █████╗█████╔╝ ██║ █╗ ██║█████╗  ███████╗   ██║   ", CYAN))
    print(c("  ╚════╝██╔═██╗ ██║███╗██║██╔══╝  ╚════██║   ██║   ", CYAN))
    print(c("        ██║  ██╗╚███╔███╔╝███████╗███████║   ██║   ", CYAN))
    print(c("        ╚═╝  ╚═╝ ╚══╝╚══╝ ╚══════╝╚══════╝   ╚═╝  ", CYAN))
    print(c("                     -Built by AragonSpirit | v-pre-1.1.1", BOLD))
    print()

    # --- Config ---
    cfg = load_config()
    if args.offset    is not None: cfg["offset_ms"]      = args.offset
    if args.countdown is not None: cfg["countdown"]       = args.countdown
    if args.threshold is not None: cfg["audio_threshold"] = args.threshold

    # --- Calibration ---
    needs_calib = not os.path.exists(CONFIG_FILE) or not cfg.get("cell_centers")
    if args.calibrate or needs_calib:
        if needs_calib and not args.calibrate:
            print(c("  [NOTICE] No calibration data found — launching calibration wizard.", YELLOW))
        cfg["dpi_aware_calibrated"] = True
        cfg = calibrate(cfg)
    elif not cfg.get("dpi_aware_calibrated"):
        # Old calibration was captured before the DPI fix — those coordinates are
        # in logical pixels and will land in the wrong place on a scaled display.
        print(c("  [WARNING] Your saved calibration pre-dates the DPI fix (v1.1.1).", YELLOW))
        print(c("            On a 125%+ scaled display those coordinates will be wrong.", YELLOW))
        print(c("            Run with -c to re-calibrate and fix mouse accuracy.", YELLOW))
        print()

    # --- Map validation ---
    if not args.sspm:
        parser.print_help()
        print(c("\n  [ERROR] Please provide a .sspm file path.", RED))
        sys.exit(1)
    if not Path(args.sspm).is_file():
        print(c(f"\n  [ERROR] File not found: {args.sspm}", RED))
        sys.exit(1)

    # --- Load map ---
    notes = load_map(args.sspm)
    if not notes:
        print(c("  [ERROR] No notes found in this map.", RED))
        sys.exit(1)

    # --- Settings summary ---
    loopback_ready = AUDIO_SYNC_AVAILABLE and find_loopback_device() is not None
    if args.no_audio_sync:
        audio_status = "Disabled (--no-audio-sync flag)"
    elif not AUDIO_SYNC_AVAILABLE:
        audio_status = "Unavailable — install sounddevice"
    elif not loopback_ready:
        audio_status = "Unavailable — no WASAPI loopback device (enable Stereo Mix or use VB-Cable)"
    else:
        audio_status = "Active (WASAPI loopback)"

    calib_pts = len(cfg.get("cell_centers", [])) * 3

    print(c("  Active settings:", DIM))
    print(c(f"    Calibration  : {calib_pts} / 9 points captured", DIM))
    print(c(f"    Audio sync   : {audio_status}", DIM))
    print(c(f"    Timing offset: {cfg['offset_ms']} ms", DIM))
    print(c(f"    Quit: F3  |  Pause / Resume: ESC", DIM))
    print()

    # --- Confirmation ---
    try:
        input(c("  Press ENTER to arm the player (or Ctrl+C to cancel)... ", BOLD))
    except KeyboardInterrupt:
        print(c("\n  Cancelled.", YELLOW))
        sys.exit(0)

    # --- Run ---
    player = AutoPlayer(notes, cfg)
    try:
        player.run(use_audio_sync=not args.no_audio_sync)
    except KeyboardInterrupt:
        print(c("\n  Interrupted via Ctrl+C.", YELLOW))
    except pyautogui.FailSafeException:
        print(c("\n  PyAutoGUI fail-safe triggered (mouse hit top-left corner).", YELLOW))
    finally:
        keyboard.remove_all_hotkeys()


if __name__ == "__main__":
    main()



# TODO: rewrite the code & README.md for version 1.1.1 -> Audio Handling; New Calibration System; Note hitting problem fix