# Picker Knob Calibration

The picker supports per-knob calibration to handle variations in voltage ranges between different potentiometers. This eliminates the "straddling threshold" problem where knobs oscillate between adjacent positions.

## Quick Start

Use the existing calibration file:
```bash
PYTHONPATH=. python picker/run_picker.py --calibration picker/mcp3008_calibration.json --verbose
```

## Creating New Calibration

1. **Run the calibrator:**
   ```bash
   PYTHONPATH=. python picker/calibrate.py --outfile my_picker_calibration.json
   ```

2. **Follow the interactive process:**
   - Move each knob (CH0, CH1, CH2, CH4, CH5, CH6) through ALL positions
   - Hold each position steady for ~1 second
   - The tool detects stable voltages and clusters them as positions
   - Press Enter when finished

3. **Use the calibration:**
   ```bash
   PYTHONPATH=. python picker/run_picker.py --calibration my_picker_calibration.json
   ```

## How It Works

- **Without calibration:** Knobs use linear voltage division (0-3.3V ÷ 12 positions)
- **With calibration:** Each knob uses its own measured voltage breakpoints
- **Position detection:** Uses midpoint thresholds between measured positions
- **Eliminates oscillation:** Accounts for actual hardware voltage ranges

## Calibration File Format

```json
{
  "vref": 3.3,
  "channels": {
    "0": [0.0, 0.297, 0.594, 0.876, ...],  // Measured voltages for CH0
    "1": [0.0, 0.297, 0.597, 0.897, ...],  // Measured voltages for CH1
    ...
  }
}
```

## Troubleshooting

- **"No positions detected":** Move knobs more slowly, hold positions longer
- **Too few positions:** Increase `--cluster-tol` to merge nearby readings
- **Unstable readings:** Decrease `--settle-threshold` for stricter stability

## Advanced Options

```bash
python picker/calibrate.py \
  --settle-threshold 0.01 \    # Stricter stability (less voltage noise)
  --cluster-tol 0.08 \         # More tolerant clustering
  --rate 30                    # Lower sample rate
```