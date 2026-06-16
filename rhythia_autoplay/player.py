import threading
import time

import keyboard
import pyautogui
import pydirectinput

from .audio import AUDIO_SYNC_AVAILABLE, find_loopback_device, wait_for_audio
from .constants import BOLD, DIM, GREEN, RED, YELLOW, c
from .coordinates import note_to_screen


class AutoPlayer:
    def __init__(self, notes: list, cfg: dict):
        self.notes = notes
        self.cfg = cfg
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._paused_at = 0.0
        self._pause_elapsed = 0.0

        keyboard.add_hotkey(cfg["quit_key"],  self._on_quit,  suppress=True)
        keyboard.add_hotkey(cfg["pause_key"], self._on_pause, suppress=True)

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE    = 0

    def _on_quit(self) -> None:
        print(c("\n  [F3] Emergency stop!", RED))
        self._stop.set()
        self._pause.clear()

    def _on_pause(self) -> None:
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

    def _wait_until(self, target_perf: float) -> bool:
        """
        Sleep until *target_perf* (a perf_counter value), accounting for any
        time spent paused.  Returns False immediately if the user quits.
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

    def _sync_audio(self) -> float | None:
        """
        Try to auto-detect song start via WASAPI loopback.
        Returns perf_counter at detection, or None (caller falls back to countdown).
        """
        if not AUDIO_SYNC_AVAILABLE:
            print(c("  [AUDIO] sounddevice not installed - falling back to countdown.", YELLOW))
            return None

        if find_loopback_device() is None:
            print(c("  [AUDIO] No WASAPI loopback device found - falling back to countdown.", YELLOW))
            print(c("  [TIP]   Enable 'Stereo Mix' in Sound settings, or install VB-Cable.", DIM))
            return None

        print(c(f"\n  Start the map in Rhythia whenever you are ready.", YELLOW))
        detected = wait_for_audio(self._stop, self.cfg)

        if self._stop.is_set():
            return None
        if detected is None:
            print(c("  [AUDIO] Timed out - falling back to countdown.", YELLOW))
            return None

        print(c("  [AUDIO] Song detected - syncing!", GREEN))
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

    def run(self, use_audio_sync: bool = True, speed: float = 1.0) -> None:
        """
        Play the map.

        Parameters
        ----------
        use_audio_sync : bool
            When True, attempt WASAPI loopback detection before falling back
            to the countdown timer.
        speed : float
            Playback speed multiplier.  Must match the in-game speed you set
            in Rhythia before starting the map.
            - 1.0  → normal speed (default)
            - 0.75 → 75 % speed  (slower, notes fire later)
            - 1.5  → 150 % speed (faster, notes fire earlier)
            Note timestamps are divided by this value, so the bot fires each
            click proportionally sooner or later.
        """
        if speed <= 0:
            raise ValueError(f"speed must be > 0, got {speed}")

        offset_s = self.cfg["offset_ms"] / 1000.0

        # Determine t=0 (the moment the song begins).
        start = None
        if use_audio_sync:
            start = self._sync_audio()
        if start is None:
            if self._stop.is_set():
                return
            start = self._sync_countdown()
        if start is None or self._stop.is_set():
            return

        # Playback loop.
        total  = len(self.notes)
        played = 0

        for x, y, ms in self.notes:
            if self._stop.is_set():
                break

            # Divide the note timestamp by the speed multiplier so that at 2×
            # a note originally at t=1000 ms fires at t=500 ms, etc.
            target_perf = start + (ms / 1000.0 / speed) + offset_s
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