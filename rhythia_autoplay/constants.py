# --- Color codes ---
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"


def c(text, colour) -> str:
    """Wrap *text* in an ANSI color code and reset it afterward."""
    return f"{colour}{text}{RESET}"


# --- 9-point calibration labels (row-major order) ---
CELL_LABELS = [
    ["TOP-LEFT",    "TOP-CENTER",    "TOP-RIGHT"   ],
    ["MIDDLE-LEFT", "MIDDLE-CENTER", "MIDDLE-RIGHT"],
    ["BOTTOM-LEFT", "BOTTOM-CENTER", "BOTTOM-RIGHT"],
]

# Visual reference printed during the calibration wizard.
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

# --- Rhythia difficulty IDs → human-readable names ---
DIFFICULTY_NAMES = {
    0: "N/A",
    1: "Easy",
    2: "Medium",
    3: "Hard",
    4: "Logic",
    5: "Tasukete",
}
