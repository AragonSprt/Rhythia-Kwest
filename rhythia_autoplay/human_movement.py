import math
import random
import time
import threading

class HumanizedCursor:
    def __init__(self,
                 note_radius: int = 30,
                 jitter_sigma_ms: float = 5.0,
                 offset_percent_range: tuple = (0.5, 2.0),
                 wobble_amplitude: float = 2.0,
                 wobble_freq: float = 8.0):
        self.note_radius = note_radius
        self.jitter_sigma_ms = jitter_sigma_ms
        self.offset_range = offset_percent_range
        self.wobble_amp = wobble_amplitude
        self.wobble_freq = wobble_freq

        self._lock = threading.Lock()
        self._current_plan = None   # dict with all curve data, or None

    def compute_jitter(self) -> float:
        """Return a Gaussian jitter in milliseconds, clamped to ±15 ms."""
        jitter = random.gauss(0, self.jitter_sigma_ms)
        return max(-15.0, min(15.0, jitter))

    def plan_move(self, start_pos: tuple, target_note_pos: tuple,
                  start_time: float, end_time: float):
        """
        Plan a new movement curve.

        :param start_pos: The current cursor (x, y)
        :param target_note_pos: pixel center of the target note (x, y)
        :param start_time: perf_counter when movement should start
        :param end_time: perf_counter when we must arrive (jittered hit time)
        """
        # Random radial offset (off‑center)
        pct = random.uniform(*self.offset_range) / 100.0
        angle = random.uniform(0, 2 * math.pi)
        offset = (math.cos(angle) * self.note_radius * pct,
                  math.sin(angle) * self.note_radius * pct)
        target = (target_note_pos[0] + offset[0],
                  target_note_pos[1] + offset[1])

        # Cubic Bézier control points: one near start, one near target,
        # perturbed perpendicular to the straight line.
        dx = target[0] - start_pos[0]
        dy = target[1] - start_pos[1]
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            dist = 1.0
        # Perpendicular unit vector
        perp = (-dy / dist, dx / dist)

        curve_strength = random.uniform(0.2, 0.5) * dist
        cp1 = (start_pos[0] + perp[0] * curve_strength * random.uniform(-1, 1),
               start_pos[1] + perp[1] * curve_strength * random.uniform(-1, 1))
        cp2 = (target[0] + perp[0] * curve_strength * random.uniform(-0.5, 0.5),
               target[1] + perp[1] * curve_strength * random.uniform(-0.5, 0.5))

        plan = {
            'start': start_pos,
            'end': target,
            'cp1': cp1,
            'cp2': cp2,
            't0': start_time,
            't1': end_time,
        }
        with self._lock:
            self._current_plan = plan

    def get_position(self) -> tuple:
        """
        Return the cursor position at this exact instant.
        Call this from the movement thread every tick.
        """
        with self._lock:
            plan = self._current_plan
        if plan is None:
            return None   # no movement planned yet

        now = time.perf_counter()
        t0 = plan['t0']
        t1 = plan['t1']
        if t1 <= t0:
            # Edge case (instant move): just return end point
            return plan['end']

        elapsed = now - t0
        if elapsed <= 0:
            return plan['start']

        # Parametric t along the curve (0→1), clamped
        t = min(1.0, elapsed / (t1 - t0))

        # Ease in/out (smoothstep) for more natural speed profile
        t_eased = t * t * (3 - 2 * t)

        # Cubic Bézier
        p0 = plan['start']
        p1 = plan['end']
        p2 = plan['cp1']
        p3 = plan['cp2']
        u = 1 - t_eased
        bx = (u**3 * p0[0] + 3*u**2*t_eased * p2[0] +
              3*u*t_eased**2 * p3[0] + t_eased**3 * p1[0])
        by = (u**3 * p0[1] + 3*u**2*t_eased * p2[1] +
              3*u*t_eased**2 * p3[1] + t_eased**3 * p1[1])

        # Depth wobble (vertical oscillation, only active before arrival)
        if t < 1.0:
            wobble = math.sin(elapsed * self.wobble_freq * 2 * math.pi) * self.wobble_amp
            by += wobble

        return (bx, by)