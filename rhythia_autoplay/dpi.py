
#  DPI AWARENESS
#  Must be called before any coordinate is read or written.


import ctypes


def set_dpi_aware() -> None:
    """
    Tell Windows that this process handles DPI scaling itself, so all Win32
    coordinate APIs (GetCursorPos, SetCursorPos, SendInput, ...) return and
    accept RAW PHYSICAL pixels instead of scaled logical pixels.

    Without this, at 150 % scaling every coordinate is off by ×1.5:
    pyautogui reads logical pixels during calibration, but pydirectinput
    sends physical pixels during playback → mouse lands in the wrong place.

    We try the modern per-monitor-v2 API first, then the legacy fallback.
    """
    try:
        # Windows 8.1+  PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except AttributeError:
        pass
    try:
        # Windows legacy fallback
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        pass  # non-Windows: no-op
