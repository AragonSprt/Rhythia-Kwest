import sys
import time
import json
import os
import threading
import argparse
from pathlib import Path


# --- Third-party ---
try:
    import pyautogui
    import keyboard
    import pydirectinput
    import pysspm_rhythia

    # Compatibility shim for pysspm-rhythia v2
    sys.modules["pysspm"] = pysspm_rhythia.pysspm
    from pysspm_rhythia import read_sspm

except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("  Run:  pip install -r requirements.txt")
    print("  Notice: Careful with the old 'pysspm' package (ignore if you're using v2).")
    sys.exit(1)

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False


# --- Constants ---
CONFIG_FILE = "utils/rhythia_config.json"  # saved automatically after calibration

DEFAULT_CONFIG = {
    # Pixel coordinates of the playfield on your monitor.
    "grid_left":   660,    # x of the LEFT edge of the 3×3 grid
    "grid_top":    140,    # y of the TOP edge of the 3×3 grid
    "grid_width":  600,    # pixel width of the grid (all 3 columns)
    "grid_height": 600,    # pixel height of the grid (all 3 rows)

    # How many seconds to count down before the first note fires.
    "countdown":   5,

    # Global timing offset in milliseconds.
    "offset_ms":   0,

    # Mouse move duration in seconds. 0 = instant (recommended for accuracy).
    "move_duration": 0.0,

    # Hotkeys (keyboard library names)
    "quit_key":  "f3",
    "pause_key": "escape",
}


#  --- Color helpers for terminal output ---
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def c(text, colour): return f"{colour}{text}{RESET}"


#  --- Useful functions  ---
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            # Merge with defaults so new keys are never missing
            cfg = {**DEFAULT_CONFIG, **saved}
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    print(c(f"  Config saved → {CONFIG_FILE}", DIM))

def note_to_screen(x: float, y: float, cfg: dict) -> tuple[int, int]:
    """
    The formula for converting a note position (x, y) to pixel coordinates::
        x = 0 → left-center of column 0
        x = 1 → center of column 1
        x = 2 → right-center of column 2
    """
    cell_w = cfg["grid_width"]  / 3
    cell_h = cfg["grid_height"] / 3

    px = cfg["grid_left"] + (x + 0.5) * cell_w
    py = cfg["grid_top"]  + (y + 0.5) * cell_h
    return int(px), int(py)

def calibrate(cfg: dict) -> dict:
    print()
    print(c("  --- Grid Calibration ---", BOLD))
    print("  Switch over to the Rhythia window and focus it.")
    print("  Hover the mouse over the top-left and bottom-right corner.")
    print("  Press ENTER to capture the coordinates.")
    print()

    def capture(label: str) -> tuple[int, int]:
        input(f"  Hover your mouse over the {c(label, YELLOW)} corner of the grid and press ENTER...")
        pos = pyautogui.position()
        print(c(f"    Captured: ({pos.x}, {pos.y})", DIM))
        return pos.x, pos.y

    x1, y1 = capture("TOP-LEFT")
    x2, y2 = capture("BOTTOM-RIGHT")

    cfg["grid_left"]   = min(x1, x2)
    cfg["grid_top"]    = min(y1, y2)
    cfg["grid_width"]  = abs(x2 - x1)
    cfg["grid_height"] = abs(y2 - y1)

    print()
    print(c("  Calibration complete:", GREEN))
    print(f"    Left:   {cfg['grid_left']} px")
    print(f"    Top:    {cfg['grid_top']} px")
    print(f"    Width:  {cfg['grid_width']} px")
    print(f"    Height: {cfg['grid_height']} px")
    print()

    save_config(cfg)
    return cfg


# --- Map loading ---
DIFFICULTY_NAMES = {
    0: "N/A",
    1: "Easy",
    2: "Medium",
    3: "Hard",
    4: "Logic",
    5: "Tasukete",
}

def load_map(path: str):
    print(c(f"\n  Reading: {path}", DIM))
    try:
        sspm = read_sspm(path)
    except Exception as e:
        print(c(f"[ERROR] Failed to read SSPM: {e}", RED))
        sys.exit(1)

    notes = sorted(sspm.notes, key=lambda n: n[2])  # sort by timestamp

    diff_id = sspm.difficulty.value if hasattr(sspm.difficulty, "value") else 0
    diff    = DIFFICULTY_NAMES.get(diff_id, "Unknown")
    dur_s   = sspm.last_ms / 1000
    quantum = any(isinstance(x, float) and x != int(x) for x, y, ms in notes)

    print()
    print(c("  ╔═══════════════════════════════════════╗", CYAN))
    print(c(f"  ║  Map   : ", CYAN) + c(sspm.map_name, BOLD)              + c(" " * max(0, 29 - len(sspm.map_name)) + "║", CYAN))
    print(c(f"  ║  Mapper: ", CYAN) + ", ".join(sspm.mappers)              + c(" " * max(0, 29 - len(", ".join(sspm.mappers))) + "║", CYAN))
    print(c(f"  ║  Diff  : {diff:<29}║", CYAN))
    print(c(f"  ║  Notes : {len(notes):<29}║", CYAN))
    print(c(f"  ║  Length: {dur_s:.1f}s{'':<25}║", CYAN))
    print(c(f"  ║  Quantum: {'Yes' if quantum else 'No':<28}║", CYAN))
    print(c("  ╚═══════════════════════════════════════╝", CYAN))
    print()

    return notes


# --- The Automator2000 ---
class AutoPlayer:
    def __init__(self, notes: list, cfg: dict):
        self.notes      = notes
        self.cfg        = cfg
        self._stop      = threading.Event()
        self._pause     = threading.Event()
        self._paused_at = 0.0
        self._pause_elapsed = 0.0

        # Register hotkeys
        keyboard.add_hotkey(cfg["quit_key"],  self._on_quit,  suppress=True)
        keyboard.add_hotkey(cfg["pause_key"], self._on_pause, suppress=True)

        # [UNUSED] Move mouse to top-left corner to hard-abort
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE    = 0  # remove built-in delay between calls

    def _on_quit(self):
        print(c("\n  [ESC] Emergency stop!", RED))
        self._stop.set()
        self._pause.clear()   # unblock any waiting sleep

    def _on_pause(self):
        if self._stop.is_set():
            return
        if self._pause.is_set():
            # Resume
            paused_for = time.perf_counter() - self._paused_at
            self._pause_elapsed += paused_for
            self._pause.clear()
            print(c("  [F3] Resumed.", GREEN))
        else:
            # Pause
            self._paused_at = time.perf_counter()
            self._pause.set()
            print(c("  [F3] Paused. Press F3 again to resume.", YELLOW))

    def _wait_until(self, target_perf: float):
        while True:
            if self._stop.is_set():
                return False

            # If paused, just spin-wait until unpaused
            if self._pause.is_set():
                time.sleep(0.01)
                continue

            remaining = (target_perf + self._pause_elapsed) - time.perf_counter()

            if remaining <= 0:
                return True

            # Sleep in small chunks to stay responsive to pause/quit
            time.sleep(min(remaining, 0.005))


# --- Main playback loop ---
    def run(self):
        cfg       = self.cfg
        countdown = cfg["countdown"]
        offset_s  = cfg["offset_ms"] / 1000.0

        # ── Countdown ────────────────────────────────────────────────────────
        print(c(f"  Focus the Rhythia window now!", YELLOW))
        print(c(f"  Starting in {countdown} seconds  (F3 = quit, ESC = pause)\n", DIM))

        t0 = time.perf_counter()
        for remaining in range(countdown, 0, -1):
            print(c(f"  {remaining}...", BOLD), end="\r", flush=True)
            target = t0 + (countdown - remaining + 1)
            if not self._wait_until(target):
                return

        print(c("  GO!                  ", GREEN))
        start = time.perf_counter()  # t=0 aligns with first note at ms=0

        total  = len(self.notes)
        played = 0

        for x, y, ms in self.notes:
            if self._stop.is_set():
                break

            # When should this note fire?
            target_perf = start + (ms / 1000.0) + offset_s

            if not self._wait_until(target_perf):
                break   # quit pressed

            # Move mouse to note position using DirectInput (better game compatibility than pyautogui)
            px, py = note_to_screen(x, y, cfg)
            pydirectinput.moveTo(px, py, duration=cfg["move_duration"])

            pydirectinput.click()

            played += 1

            # Prin progress every 50 notes (avoid print spam on dense maps)
            if played % 50 == 0 or played == total:
                pct = played / total * 100
                bar = ("█" * int(pct // 5)).ljust(20)
                print(c(f"  [{bar}] {pct:5.1f}%  ({played}/{total})", DIM),
                      end="\r", flush=True)

        keyboard.remove_all_hotkeys()
        print()  # newline after progress bar

        if self._stop.is_set():
            print(c("\n  Stopped early.", YELLOW))
        else:
            print(c("\n  Map complete! ✓", GREEN))


# --- Entry point ---
def main():
    parser = argparse.ArgumentParser(
        description="Official Rhythia SSPM Auto-Player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "sspm",
        nargs="?",
        help="Path to the .sspm map file",
    )
    parser.add_argument(
        "-c","--calibrate",
        action="store_true",
        help="Re-run the grid calibration wizard",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=None,
        metavar="MS",
        help="Override timing offset in milliseconds (e.g. --offset -50)",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=None,
        metavar="SEC",
        help="Override countdown duration in seconds",
    )
    args = parser.parse_args()

    print()
    print(c("  ██████╗ ██╗  ██╗██╗   ██╗████████╗██╗  ██╗██╗ █████╗ ", CYAN))
    print(c("  ██╔══██╗██║  ██║╚██╗ ██╔╝╚══██╔══╝██║  ██║██║██╔══██╗", CYAN))
    print(c("  ██████╔╝███████║ ╚████╔╝    ██║   ███████║██║███████║", CYAN))
    print(c("  ██╔══██╗██╔══██║  ╚██╔╝     ██║   ██╔══██║██║██╔══██║", CYAN))
    print(c("  ██║  ██║██║  ██║   ██║      ██║   ██║  ██║██║██║  ██║", CYAN))
    print(c("  ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝", CYAN))
    print(c("                        -Built by AragonSpirit | v1.0.0", BOLD))
    print()

    cfg = load_config()

    if args.offset is not None:
        cfg["offset_ms"] = args.offset
    if args.countdown is not None:
        cfg["countdown"] = args.countdown

    first_run = not os.path.exists(CONFIG_FILE)

    if args.calibrate or first_run:
        if first_run:
            print(c("  [NOTICE] You have to calibrate the tool for your first usage.", YELLOW))
        cfg = calibrate(cfg)

    # --- Map validation  ---
    if not args.sspm:
        parser.print_help()
        print(c("\n  [ERROR] Please provide a .sspm file path.", RED))
        sys.exit(1)

    if not Path(args.sspm).is_file():
        print(c(f"\n  [ERROR] File not found: {args.sspm}", RED))
        sys.exit(1)

    # --- Load map  ---
    notes = load_map(args.sspm)

    if not notes:
        print(c("  [ERROR] No notes found in this map.", RED))
        sys.exit(1)

    # --- Config summary ---
    print(c("  Active settings:", DIM))
    print(c(f"    Grid  : ({cfg['grid_left']}, {cfg['grid_top']})  "
            f"{cfg['grid_width']}×{cfg['grid_height']} px", DIM))
    print(c(f"    Offset: {cfg['offset_ms']} ms  |  Countdown: {cfg['countdown']}s", DIM))
    print(c(f"    Quit  : F3  |  Pause/Resume: ESC", DIM))
    print()

    # --- Confirmation prompt ---
    try:
        input(c("  Press ENTER to start (or Ctrl+C to cancel)... ", BOLD))
    except KeyboardInterrupt:
        print(c("\n  Cancelled.", YELLOW))
        sys.exit(0)

    # --- Ultra mega intense gameplay ---
    player = AutoPlayer(notes, cfg)
    try:
        player.run()
    except KeyboardInterrupt:
        print(c("\n  Interrupted via Ctrl+C.", YELLOW))
    except pyautogui.FailSafeException:
        print(c("\n  PyAutoGUI fail-safe triggered (mouse hit top-left corner).", YELLOW))
    finally:
        keyboard.remove_all_hotkeys()


if __name__ == "__main__":
    main()