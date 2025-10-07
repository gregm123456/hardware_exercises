"""Hardware abstraction for picker: ADC reading, knob->position mapping, and button reads.

Provides a SimulatedMCP3008 for development and tests, and a KnobMapper class that
maps ADC readings to discrete positions with hysteresis and simple debounce.
"""
from __future__ import annotations

import time
from typing import Dict, Callable, List, Tuple, Optional
from dataclasses import dataclass, field

# We'll support 10-bit (0..1023) ADC values by default.
DEFAULT_ADC_MAX = 1023


class SimulatedMCP3008:
    """Simple simulator for MCP3008-like ADC channels.

    Usage: set_channel(channel, value) to change a channel's reading.
    Call read(channel) to get the current value.
    """

    def __init__(self, channels: Optional[List[int]] = None, max_value: int = DEFAULT_ADC_MAX):
        self.max_value = max_value
        self.channels = {ch: 0 for ch in (channels or list(range(8)))}

    def set_channel(self, ch: int, val: int):
        if ch not in self.channels:
            raise KeyError(f"Channel {ch} not in simulator")
        self.channels[ch] = max(0, min(self.max_value, int(val)))

    def read(self, ch: int) -> int:
        return self.channels.get(ch, 0)


@dataclass
class Calibration:
    adc_min: int = 0
    adc_max: int = DEFAULT_ADC_MAX
    inverted: bool = False
    positions: int = 12
    hysteresis: float = 0.015  # fraction of full-scale


@dataclass
class KnobState:
    last_raw: int = 0
    last_pos: int = 0
    stable_count: int = 0
    last_change_time: float = 0.0


class KnobMapper:
    """Map raw ADC values to discrete positions with hysteresis and debounce.

    Usage:
      mapper = KnobMapper(calibration)
      pos = mapper.map(adc_value)

    The mapper requires repeated calls, and uses an internal stable-count to avoid
    jitter. For very responsive UIs, tune the poll_hz and stable_count requirement.
    """

    def __init__(self, calib: Calibration, stable_required: int = 2):
        self.calib = calib
        self.stable_required = max(1, stable_required)
        self.state = KnobState()

    def normalize(self, raw: int) -> float:
        denom = max(1, self.calib.adc_max - self.calib.adc_min)
        v = (raw - self.calib.adc_min) / denom
        v = max(0.0, min(1.0, v))
        if self.calib.inverted:
            v = 1.0 - v
        return v

    def raw_to_pos(self, raw: int) -> int:
        v = self.normalize(raw)
        pos_f = v * self.calib.positions
        pos = int(pos_f)  # floor
        if pos >= self.calib.positions:
            pos = self.calib.positions - 1
        if pos < 0:
            pos = 0
        return pos

    def map(self, raw: int) -> Tuple[int, bool]:
        """Map a raw ADC value to a debounced position.

        Returns (position, changed) where changed is True when the stable mapping
        has advanced to a new position.
        """
        pos = self.raw_to_pos(raw)
        changed = False

        # quick path: if same as last reported pos, reset stable_count
        if pos == self.state.last_pos:
            self.state.stable_count = 0
            self.state.last_raw = raw
            return pos, False

        # if pos equals last_raw-derived pos but not last_pos, check for stability
        if pos == self.raw_to_pos(self.state.last_raw):
            # bump stable counter
            self.state.stable_count += 1
        else:
            # reset stability and remember raw
            self.state.stable_count = 1
            self.state.last_raw = raw

        if self.state.stable_count >= self.stable_required:
            # Accept the change
            self.state.last_pos = pos
            self.state.stable_count = 0
            self.state.last_change_time = time.time()
            changed = True

        return self.state.last_pos, changed


class HW:
    """High-level HW interface used by the picker core.

    Exposes:
      - read_positions() -> Dict[channel_name, position]
      - read_buttons() -> Dict[channel_name, bool]

    Channels naming: CH0..CH7 mapping to adc channel indices 0..7.
    """

    KNOB_CHANNELS = [0, 1, 2, 4, 5, 6]
    BUTTON_CHANNELS = {3: "GO", 7: "RESET"}

    def __init__(self, adc_reader=None, calib_map: Dict[int, Calibration] = None, poll_hz: int = 80, adc_spi_port: int = 0, adc_spi_device: int = 1):
        # If an adc_reader was provided use it. Otherwise attempt to create a real
        # Adafruit_MCP3008 reader (SPI). If that fails, fall back to the simulator.
        if adc_reader is not None:
            self.adc = adc_reader
        else:
            try:
                import Adafruit_MCP3008
                import Adafruit_GPIO.SPI as SPI

                # Hardware setup: ADC (MCP3008) is on CE1, epaper is on CE0
                ADC_SPI_PORT = adc_spi_port
                ADC_SPI_DEVICE = adc_spi_device  # CE1 for MCP3008/ADC
                spi = SPI.SpiDev(ADC_SPI_PORT, ADC_SPI_DEVICE)
                # set a conservative clock speed used elsewhere in this repo
                try:
                    spi.set_clock_hz(1350000)
                except Exception:
                    pass
                mcp = Adafruit_MCP3008.MCP3008(spi=spi)
                self.adc = mcp
            except Exception:
                # Hardware libs not available or failed; use simulator
                self.adc = SimulatedMCP3008()
        self.poll_hz = poll_hz
        self.interval = 1.0 / max(1, poll_hz)
        self.calib_map = calib_map or {ch: Calibration() for ch in range(8)}
        # Determine stable_required from poll_hz: higher poll rates need more samples
        # to consider a reading stable. Keep a sensible minimum of 2 samples.
        try:
            stable_required = max(2, int(self.poll_hz // 20))
        except Exception:
            stable_required = 2
        self.mappers = {ch: KnobMapper(self.calib_map.get(ch, Calibration()), stable_required=stable_required) for ch in self.KNOB_CHANNELS}

        # Button thresholds: read ADC and compare > threshold to detect press.
        # Default threshold is 0.2 of full-scale (can be tuned per channel via calib_map)
        self.button_threshold = {ch: 0.2 for ch in self.BUTTON_CHANNELS}

    def read_raw(self, ch: int) -> int:
        """Read raw ADC counts from the underlying ADC reader.

        Support different reader APIs: Adafruit_MCP3008 provides `read_adc(ch)`,
        while our simulator implements `read(ch)`. Try common method names.
        """
        # prefer read_adc (Adafruit_MCP3008)
        if hasattr(self.adc, 'read_adc'):
            return int(self.adc.read_adc(ch))
        # some implementations may provide read() which our simulator uses
        if hasattr(self.adc, 'read'):
            return int(self.adc.read(ch))
        # fallback: try generic get method
        if hasattr(self.adc, 'get'):
            return int(self.adc.get(ch))
        raise AttributeError("ADC reader has no compatible read method (expected read_adc or read)")

    def read_positions(self) -> Dict[int, Tuple[int, bool]]:
        """Read and map all knobs. Returns dict {ch: (pos, changed)}"""
        out = {}
        for ch in self.KNOB_CHANNELS:
            raw = self.read_raw(ch)
            mapper = self.mappers[ch]
            pos, changed = mapper.map(raw)
            out[ch] = (pos, changed)
        return out

    def read_buttons(self) -> Dict[str, bool]:
        """Return button states {"GO": bool, "RESET": bool} based on ADC thresholds."""
        states = {}
        for ch, name in self.BUTTON_CHANNELS.items():
            raw = self.read_raw(ch)
            calib = self.calib_map.get(ch, Calibration())
            norm = (raw - calib.adc_min) / max(1, (calib.adc_max - calib.adc_min))
            states[name] = norm > self.button_threshold.get(ch, 0.2)
        return states


# Small self-test function for manual runs
if __name__ == "__main__":
    sim = SimulatedMCP3008()
    # drive CH0 through a few values and print mapping
    sim.set_channel(0, 0)
    hw = HW(adc_reader=sim)
    for v in [0, 50, 100, 200, 400, 600, 800, 1023]:
        sim.set_channel(0, v)
        pos, changed = hw.read_positions()[0]
        print(f"raw={v} -> pos={pos} changed={changed}")
        time.sleep(0.05)
