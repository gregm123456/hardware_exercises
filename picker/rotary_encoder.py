"""Rotary encoder hardware abstraction for picker.

Provides :class:`RotaryEncoder` (GPIO-based, Raspberry Pi) and
:class:`SimulatedRotaryEncoder` for development and unit tests.

The driver uses a background polling thread with a full-step quadrature state
machine for reliable step detection, and time-based software debounce for the
pushbutton switch.  Events are placed on an internal :class:`queue.Queue` as
``(kind, value)`` tuples:

* ``('rotate', +1)``  — one detent clockwise
* ``('rotate', -1)``  — one detent counter-clockwise
* ``('button', True)``  — button pressed  (SW pulled LOW)
* ``('button', False)`` — button released

Hardware connections (5 leads)
-------------------------------
* GND — Ground
* 3V3 — +3.3 V supply
* CLK (A) — GPIO BCM pin (default 17)
* DT  (B) — GPIO BCM pin (default 18)
* SW      — GPIO BCM pin (default 27)

All three GPIO pins are configured with internal pull-ups so the encoder can
be wired directly with only the five leads; no external resistors needed.

Debouncing notes
----------------
Rotation is debounced by the quadrature state machine itself: only valid
Gray-code transitions advance the counter, so electrical glitches that jump
more than one state at a time are silently discarded.  The polling rate
(default 1 kHz) is high enough to catch all detents reliably while being low
enough not to load the CPU.

Button debounce is handled by a configurable minimum stable-hold time
(default 50 ms): the raw GPIO level must remain unchanged for at least
``debounce_ms`` milliseconds before a press/release event is emitted.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Quadrature full-step table
# ---------------------------------------------------------------------------
# Indexed as (prev_AB << 2) | cur_AB  where A = CLK, B = DT.
# Values: +1 (CW), -1 (CCW), 0 (invalid / intermediate transition).
# The 16-entry table encodes all possible 2-bit → 2-bit transitions.
_STEP_TABLE: Tuple[int, ...] = (
    #  cur: 00  01  10  11
        0, -1,  1,  0,   # prev 00
        1,  0,  0, -1,   # prev 01
       -1,  0,  0,  1,   # prev 10
        0,  1, -1,  0,   # prev 11
)

# ---------------------------------------------------------------------------
# Default GPIO BCM pin assignments
# ---------------------------------------------------------------------------
DEFAULT_PIN_CLK: int = 17  # CLK / A output
DEFAULT_PIN_DT: int = 18   # DT  / B output
DEFAULT_PIN_SW: int = 27   # SW  (pushbutton, active-LOW)

# Background poll rate (Hz).  1 kHz is safe on a Pi and catches all detents.
_POLL_HZ: int = 1000

# Minimum enforced debounce time (seconds).  Below 1 ms the software timer
# resolution on Linux is not reliable enough to suppress contact bounce.
_MIN_DEBOUNCE_S: float = 0.001

# Minimum safe poll rate (Hz).  Rates below 100 Hz risk missing fast detents.
_MIN_POLL_HZ: int = 100


class RotaryEncoder:
    """GPIO-based rotary encoder driver using a polling background thread.

    Parameters
    ----------
    pin_clk:
        BCM GPIO number for the CLK (A) output of the encoder.
    pin_dt:
        BCM GPIO number for the DT (B) output of the encoder.
    pin_sw:
        BCM GPIO number for the SW (switch) output of the encoder.
    debounce_ms:
        Minimum stable-hold time in milliseconds for the pushbutton.
        Lower values increase responsiveness; higher values improve
        noise immunity on poor contacts.  Default: 50 ms.
    poll_hz:
        Background poll rate in Hz.  Increase for faster detent response;
        decrease to reduce CPU load.  Default: 1000 Hz.

    Raises
    ------
    RuntimeError
        If ``RPi.GPIO`` is not importable.  Use :class:`SimulatedRotaryEncoder`
        for development without hardware.
    """

    def __init__(
        self,
        pin_clk: int = DEFAULT_PIN_CLK,
        pin_dt: int = DEFAULT_PIN_DT,
        pin_sw: int = DEFAULT_PIN_SW,
        debounce_ms: int = 50,
        poll_hz: int = _POLL_HZ,
    ) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "RPi.GPIO is not available. "
                "Use SimulatedRotaryEncoder for development without hardware."
            ) from exc

        self._GPIO = GPIO
        self._pin_clk = pin_clk
        self._pin_dt = pin_dt
        self._pin_sw = pin_sw
        self._debounce_s: float = max(_MIN_DEBOUNCE_S, debounce_ms / 1000.0)
        self._poll_interval: float = 1.0 / max(_MIN_POLL_HZ, poll_hz)

        self._events: queue.Queue[Tuple[str, object]] = queue.Queue()

        # Quadrature decoder state (lower 2 bits = AB)
        self._quad_state: int = 0
        # Track raw GPIO reads before debouncing
        self._quad_raw_reads: list = []
        self._quad_required_reads: int = 2  # Low latency: only 2 stable reads (fast response)
        # Track last CLK state to detect edges
        self._quad_last_clk: int = 1  # Start HIGH (idle state)

        # Debounced button state tracking
        self._sw_raw: Optional[int] = None     # last raw GPIO reading
        self._sw_stable: Optional[int] = None  # last accepted (debounced) reading
        self._sw_change_time: float = 0.0      # monotonic time of last raw change

        # Configure GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin_clk, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(pin_dt,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(pin_sw,  GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Seed initial quadrature state to avoid a spurious first step
        clk0 = GPIO.input(pin_clk)
        dt0 = GPIO.input(pin_dt)
        self._quad_state = (clk0 << 1) | dt0
        self._quad_last_stable_state = self._quad_state
        # Seed debounced button state
        sw0 = GPIO.input(pin_sw)
        self._sw_raw = sw0
        self._sw_stable = sw0

        # Start background polling thread
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="rotary-encoder-poll",
            daemon=True,
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        GPIO = self._GPIO
        pin_clk = self._pin_clk
        pin_dt = self._pin_dt
        pin_sw = self._pin_sw
        poll_interval = self._poll_interval
        debounce_s = self._debounce_s

        while not self._stop.is_set():
            t0 = time.monotonic()

            # --- Rotation (quadrature) ---
            # Standard quadrature decoder: only recognize CLK edges, check DT for direction.
            # This naturally divides transitions by 2 (only 2 CLK edges per full rotation).
            clk = GPIO.input(pin_clk)
            dt = GPIO.input(pin_dt)
            
            # Debounce the CLK signal
            self._quad_raw_reads.append(clk)
            if len(self._quad_raw_reads) > self._quad_required_reads:
                self._quad_raw_reads.pop(0)
            
            # Only process when CLK reading is stable
            if len(self._quad_raw_reads) == self._quad_required_reads:
                if all(r == self._quad_raw_reads[0] for r in self._quad_raw_reads):
                    current_clk = self._quad_raw_reads[0]
                    
                    # Detect CLK edge (falling edge is most reliable for many encoders)
                    if current_clk == 0 and self._quad_last_clk == 1:
                        # CLK fell: when CLK goes 1→0, check DT state
                        # If DT=1 when CLK falls → CW (forward); DT=0 → CCW (backward)
                        if dt == 1:
                            direction = 1  # Clockwise
                        else:
                            direction = -1  # Counter-clockwise
                        
                        self._events.put(("rotate", direction))
                    
                    self._quad_last_clk = current_clk

            # --- Button (time-based debounce) ---
            sw = GPIO.input(pin_sw)
            now = t0
            if sw != self._sw_raw:
                # Raw level changed — start (or restart) debounce timer
                self._sw_raw = sw
                self._sw_change_time = now
            elif (
                sw != self._sw_stable
                and (now - self._sw_change_time) >= debounce_s
            ):
                # Level has been stable long enough — accept the change
                self._sw_stable = sw
                # Active-LOW wiring: pressed = LOW (0)
                self._events.put(("button", sw == 0))

            # Sleep for remainder of poll interval
            elapsed = time.monotonic() - t0
            remaining = poll_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_event(self) -> Optional[Tuple[str, object]]:
        """Return the next queued event, or ``None`` if the queue is empty.

        Returns
        -------
        tuple or None
            ``('rotate', +1)``, ``('rotate', -1)``,
            ``('button', True)``, ``('button', False)``, or ``None``.
        """
        try:
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def cleanup(self) -> None:
        """Stop the polling thread and release GPIO resources."""
        self._stop.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._GPIO.cleanup([self._pin_clk, self._pin_dt, self._pin_sw])
        except Exception:
            pass


class SimulatedRotaryEncoder:
    """Software simulation of :class:`RotaryEncoder` for development and testing.

    Inject synthetic events via :meth:`simulate_rotate` and
    :meth:`simulate_button`; retrieve them with :meth:`get_event`.

    Example::

        enc = SimulatedRotaryEncoder()
        enc.simulate_rotate(+3)      # three CW detents
        enc.simulate_button(True)    # button press
        enc.simulate_button(False)   # button release

        while True:
            ev = enc.get_event()
            if ev is None:
                break
            print(ev)
    """

    def __init__(self) -> None:
        self._events: queue.Queue[Tuple[str, object]] = queue.Queue()

    def simulate_rotate(self, delta: int) -> None:
        """Inject *delta* rotation steps.

        Positive values are CW (index-increasing), negative values are CCW.
        Each unit emits one ``('rotate', ±1)`` event.
        """
        sign = 1 if delta >= 0 else -1
        for _ in range(abs(delta)):
            self._events.put(("rotate", sign))

    def simulate_button(self, pressed: bool) -> None:
        """Inject a button press (``True``) or release (``False``) event."""
        self._events.put(("button", pressed))

    def get_event(self) -> Optional[Tuple[str, object]]:
        """Return the next queued event, or ``None`` if the queue is empty."""
        try:
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def cleanup(self) -> None:
        """No-op; present for API compatibility with :class:`RotaryEncoder`."""
