import pyautogui

from .constants import BOLD, DIM, GREEN, YELLOW, CELL_LABELS, GRID_DIAGRAM, c
from .config import save_config


def calibrate(cfg: dict) -> dict:
    """
    Walk the user through hovering over all 9 cell centers, record the pixel
    coordinates for each, persist the result, and return the updated config.
    """
    print()
    print(c("  --- 9-Point Grid Calibration ---", BOLD))
    print("  Switch to the Rhythia window (keep this terminal visible on the side).")
    print("  For each of the 9 cells you will hover over its CENTER, then press ENTER.")
    print(GRID_DIAGRAM)

    def _capture(label: str, col: int, row: int) -> list[int]:
        input(f"  [{row},{col}]  Hover over {c(label, YELLOW)} center and press ENTER...")
        pos = pyautogui.position()
        print(c(f"        → Captured: ({pos.x}, {pos.y})", DIM))
        return [pos.x, pos.y]

    # Build a 3x3 list: centers[row][col]
    centers: list[list[list[int]]] = []
    for row in range(3):
        row_data = []
        for col in range(3):
            pt = _capture(CELL_LABELS[row][col], col, row)
            row_data.append(pt)
        centers.append(row_data)

    cfg["cell_centers"] = centers

    # Derive the legacy bounding box from the 9 points (used for the summary display).
    all_x = [centers[r][col][0] for r in range(3) for col in range(3)]
    all_y = [centers[r][col][1] for r in range(3) for col in range(3)]
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
