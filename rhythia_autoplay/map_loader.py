import sys

import pysspm_rhythia
from pysspm_rhythia import read_sspm
sys.modules["pysspm"] = pysspm_rhythia.pysspm

from .constants import BOLD, CYAN, DIM, RED, DIFFICULTY_NAMES, c


def load_map(path: str) -> list:
    """
    Parse the SSPM file at *path*, print a map-info summary box, and return
    notes sorted ascending by timestamp.  Exits the process on parse error.
    """
    print(c(f"\n  Reading: {path}", DIM))
    try:
        sspm = read_sspm(path)
    except Exception as e:
        print(c(f"[ERROR] Failed to read SSPM: {e}", RED))
        sys.exit(1)

    notes = sorted(sspm.notes, key=lambda n: n[2])
    diff_id = sspm.difficulty.value if hasattr(sspm.difficulty, "value") else 0
    diff = DIFFICULTY_NAMES.get(diff_id, "Unknown")
    dur_s = sspm.last_ms / 1000
    quantum = any(isinstance(x, float) and x != int(x) for x, y, ms in notes)
    mappers_str = ", ".join(sspm.mappers)
    pad = lambda s: " " * max(0, 29 - len(s))

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
