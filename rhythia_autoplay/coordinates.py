
def note_to_screen(x: float, y: float, cfg: dict) -> tuple[int, int]:
    """
    Convert an SSPM note coordinate (x, y) to screen pixel coordinates.

    If 9-point calibration data is present (cfg["cell_centers"]):
        - Integer notes (standard grid) → direct lookup in the 3x3 table.
        - Quantum float notes → bilinear interpolation between the
                                          four surrounding calibrated centers.

    Falls back to the legacy 2-corner bounding-box formula otherwise.
    """
    centers = cfg.get("cell_centers", [])

    if not centers:
        # Legacy fallback: derive pixel position from the bounding box.
        cell_w = cfg["grid_width"]  / 3
        cell_h = cfg["grid_height"] / 3
        px = cfg["grid_left"] + (x + 0.5) * cell_w
        py = cfg["grid_top"]  + (y + 0.5) * cell_h
        return int(px), int(py)

    # Clamp to the valid [0, 2] range (handles minor quantum out-of-bounds).
    xc = max(0.0, min(2.0, float(x)))
    yc = max(0.0, min(2.0, float(y)))

    # Exact integer position → direct lookup.
    if xc == int(xc) and yc == int(yc):
        pt = centers[int(yc)][int(xc)]
        return int(pt[0]), int(pt[1])

    # Quantum position → bilinear interpolation.
    # x0/y0 are the lower-index corners; clamped so x1/y1 never exceed 2.
    x0 = min(int(xc), 1)
    y0 = min(int(yc), 1)
    x1, y1 = x0 + 1, y0 + 1

    tx = xc - x0   # fractional position within patch, x-axis [0, 1]
    ty = yc - y0   # fractional position within patch, y-axis [0, 1]

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
