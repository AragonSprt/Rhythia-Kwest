import argparse
import os
import sys
from pathlib import Path

import keyboard
import pyautogui
import pydirectinput

from .audio import AUDIO_SYNC_AVAILABLE, find_loopback_device
from .calibration import calibrate
from .config import CONFIG_FILE, load_config
from .constants import BOLD, CYAN, DIM, RED, YELLOW, c
from .dpi import set_dpi_aware
from .map_loader import load_map
from .player import AutoPlayer

# pydirectinput global settings - must be set before any input call.
pydirectinput.PAUSE    = 0.0
pydirectinput.FAILSAFE = False


def _print_banner() -> None:
    os.system("cls" if os.name == "nt" else "clear")
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
    print(c("                     -Built by AragonSpirit | v1.1.2", BOLD))
    print()


def main() -> None:
    # Must be the FIRST call - before pyautogui, pydirectinput, or any
    # coordinate read/write.  Forces physical-pixel mode on Windows,
    # fixing the DPI scaling mismatch that causes the mouse to land in the
    # wrong place on scaled displays.
    set_dpi_aware()

    parser = argparse.ArgumentParser(
        description="Official Rhythia SSPM Auto-Player",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("sspm", nargs="?", help="Path to the .sspm map file")
    parser.add_argument("-c", "--calibrate", action="store_true",
                        help="Re-run the calibration wizard")
    parser.add_argument("--no-audio-sync", action="store_true",
                        help="Skip WASAPI detection and use the countdown instead")
    parser.add_argument("--offset", type=int, default=None, metavar="MS",
                        help="Override timing offset in milliseconds (e.g. --offset -50)")
    parser.add_argument("--countdown", type=int, default=None, metavar="SEC",
                        help="Override fallback countdown duration in seconds")
    parser.add_argument("--threshold", type=float, default=None, metavar="RMS",
                        help="Override audio detection sensitivity (default 0.01)")
    parser.add_argument("--speed", type=float, default=1.0, metavar="X",
                        help="Playback speed multiplier, must match the in-game speed "
                             "(e.g. 0.75 for 75%%, 1.5 for 150%%; default: 1.0)")
    args = parser.parse_args()

    _print_banner()

    # --- Config ---
    cfg = load_config()
    if args.offset    is not None: cfg["offset_ms"]      = args.offset
    if args.countdown is not None: cfg["countdown"]       = args.countdown
    if args.threshold is not None: cfg["audio_threshold"] = args.threshold

    if args.speed <= 0:
        print(c(f"\n  [ERROR] --speed must be greater than 0 (got {args.speed}).", RED))
        sys.exit(1)

    # --- Calibration ---
    needs_calib = not os.path.exists(CONFIG_FILE) or not cfg.get("cell_centers")
    if args.calibrate or needs_calib:
        if needs_calib and not args.calibrate:
            print(c("  [NOTICE] No calibration data found - launching calibration wizard.", YELLOW))
        cfg["dpi_aware_calibrated"] = True
        cfg = calibrate(cfg)
    elif not cfg.get("dpi_aware_calibrated"):
        # Old calibration pre-dates the DPI fix - coordinates are in logical
        # pixels and will land in the wrong place on a scaled display.
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
        audio_status = "Unavailable - install sounddevice"
    elif not loopback_ready:
        audio_status = "Unavailable - no WASAPI loopback device (enable Stereo Mix or use VB-Cable)"
    else:
        audio_status = "Active (WASAPI loopback)"

    calib_pts = len(cfg.get("cell_centers", [])) * 3

    print(c("  Active settings:", DIM))
    print(c(f"    Calibration  : {calib_pts} / 9 points captured", DIM))
    print(c(f"    Audio sync   : {audio_status}", DIM))
    print(c(f"    Timing offset: {cfg['offset_ms']} ms", DIM))
    print(c(f"    Speed        : {args.speed}x", DIM))
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
        player.run(use_audio_sync=not args.no_audio_sync, speed=args.speed)
    except KeyboardInterrupt:
        print(c("\n  Interrupted via Ctrl+C.", YELLOW))
    except pyautogui.FailSafeException:
        print(c("\n  PyAutoGUI fail-safe triggered (mouse hit top-left corner).", YELLOW))
    finally:
        keyboard.remove_all_hotkeys()


if __name__ == "__main__":
    main()