# Rotary Encoder Optimization Guide

This document describes the optimizations implemented to make the rotary encoder interface feel responsive and natural, like a physical device.

## Problem Statement

Initial rotary encoder implementation had several issues:

1. **Event queuing lag** - Rotation events would queue up, causing the menu to continue scrolling after the user stopped turning the knob
2. **Full-screen flashing** - Every menu change caused a slow (~1 second) full-screen black flash using GC16 refresh mode
3. **Wrap-around confusion** - Menu would wrap from bottom to top and vice versa, making it hard to know where you were
4. **Too sensitive** - One physical detent = one menu item, making precise selection difficult
5. **Speed limiting** - Fast rotation would be ignored or cause reverse movement due to electrical noise

## Solutions Implemented

### 1. Queue Draining (Cumulative Rotation)

**Problem**: Events queued faster than display could update, causing "lag" where menu kept scrolling after user stopped.

**Solution**: Drain ALL rotation events from the queue before processing, accumulate them, and apply the net rotation all at once.

```python
# Event loop drains queue completely
cumulative_rotation = 0
while True:
    event = encoder.get_event()
    if event is None:
        break
    if kind == "rotate":
        cumulative_rotation += int(value)

# Apply cumulative result (like ADC knobs - state-based not event-based)
if cumulative_rotation != 0:
    movement = cumulative_rotation // rotation_threshold
    core.handle_rotate(movement)
```

**Inspiration**: ADC knob mode reads current position state, not event history. This makes rotary encoder behave the same way.

**Result**: Menu stops IMMEDIATELY when user stops turning. No lag, no queuing.

---

### 2. Partial Refresh with Previous Image

**Problem**: Every menu change used GC16 full-screen refresh (16-level grayscale, ~1 second, full black flash).

**Solution**: Implement true differential partial refresh using `prev_image_path` parameter.

```python
# Track previous image
prev_menu_image = [None]

def _do_display(title, items, selected_index):
    img = compose_rotary_menu(title, items, selected_index, full_screen=effective_size)
    
    # Save current for next update
    tmp_path = tempfile.gettempdir() + "/picker_rotary_menu.png"
    img.save(tmp_path)
    
    # Use partial mode with previous image
    if prev_menu_image[0] is not None:
        blit(img, "rotary-menu", rotate, mode="partial", prev_image_path=prev_menu_image[0])
    else:
        # First display - use DU mode  
        blit(img, "rotary-menu", rotate, mode="DU")
    
    prev_menu_image[0] = tmp_path
```

**Display Driver Path**:
- `run_picker.py` → `display_fast.blit(mode="partial", prev_image_path=...)`
- `display_fast.py` → `epaper_enhanced.display_image(mode="partial", prev_image_path=...)`
- `epaper_enhanced.py` → `update_waveshare.display_image(mode="partial", prev_image_path=...)`
- `update_waveshare/core.py` → Calculates bounding box difference and uses `draw_partial(DisplayModes.DU)`

**Result**: 
- Menu updates only changed regions (typically just the highlighted item text)
- Update time: ~100-200ms instead of ~1 second
- No full-screen flashing

---

### 3. Disable Wrap-Around

**Problem**: Rotating past the last item wrapped to the first item (and vice versa), causing disorientation.

**Solution**: Pass `wrap=False` to `RotaryPickerCore`.

```python
core = RotaryPickerCore(
    menus=menus,
    on_display=_do_display,
    on_action=_do_action,
    wrap=False,  # Menu sticks at ends instead of wrapping
)
```

**Result**: Menu "bottoms out" at top and bottom ends. More predictable, easier to navigate.

---

### 4. Rotation Threshold (Finer Control)

**Problem**: One physical detent = one menu item was too sensitive for menus with many items.

**Solution**: Require multiple detents to move one menu item. Implemented as a threshold with remainder tracking.

```python
rotation_threshold = 2  # Require 2 detents to move 1 menu item

# Calculate movement with remainder
movement = cumulative_rotation // rotation_threshold
remainder = cumulative_rotation % rotation_threshold

if movement != 0:
    core.handle_rotate(movement)
    cumulative_rotation = remainder  # Keep remainder for next turn
```

**Example**:
- Turn 1 detent: movement = 0, remainder = 1 (menu doesn't move yet)
- Turn 1 more detent: cumulative = 2, movement = 1, menu moves 1 item
- Turn 5 detents fast: movement = 2 (moves 2 items), remainder = 1

**Result**: More precise control, less "touchy" feel. Partial rotations accumulate naturally.

---

### 5. Directional Momentum Filtering

**Problem**: Fast rotation caused electrical noise (contact bouncing) that generated spurious reverse-direction events, making the menu jump backward or respond slowly.

**Earlier failed attempt**: High debounce requirement (5 stable reads) filtered noise BUT created a "speed limit" - turn too fast and no events were generated at all.

**Solution**: Low-latency debounce (2 stable reads) combined with **directional momentum filtering** in the event processing logic.

```python
# Track recent rotation events
rotation_history = []
history_window = 10

# When processing rotation event:
rotation_history.append(rotation_value)
if len(rotation_history) > history_window:
    rotation_history.pop(0)

# Calculate dominant direction from recent history
if len(rotation_history) >= 3:
    recent_sum = sum(rotation_history[-5:])  # Last 5 events
    
    # If strong momentum in one direction, filter out opposing noise
    if abs(recent_sum) >= 3:  # Strong directional momentum
        # Ignore events that oppose the momentum (likely noise)
        if (recent_sum > 0 and rotation_value < 0) or (recent_sum < 0 and rotation_value > 0):
            logger.debug(f"[Noise filter] Ignoring {rotation_value} event (momentum={recent_sum})")
            continue  # Skip this noisy event
```

**How it works** (like physical inertia):

1. **Track direction**: Keep history of last 10 rotation events
2. **Calculate momentum**: Sum of last 5 events indicates current direction
   - Sum ≥ +3 → Strong clockwise momentum
   - Sum ≤ -3 → Strong counter-clockwise momentum
3. **Filter opposing noise**: If you have strong CW momentum and a CCW event arrives, it's probably noise → ignore it

**Example**:
```
Events:  +1 +1 +1 +1 -1 +1 +1 +1
         └─────────┬─────────┘
           CW momentum = +7
                  ↑
         This -1 is noise → FILTERED OUT

Result: Net +7 → moves 3 items smoothly (7÷2 threshold)
```

**Why this works better than high debounce**:
- Low debounce (2 reads) = instant response to fast turns
- Momentum filter = intelligent noise rejection that doesn't block legitimate fast input
- **Fast turns get FASTER response**, slow turns stay precise

**Inspiration**: Professional rotary controllers (DJ equipment, volume knobs, industrial HMI) use this technique.

**Result**: 
- ✅ Spin fast → menu scrolls fast (no speed limit)
- ✅ Spin slow → precise control
- ✅ No spurious reverse movements
- ✅ Feels like a real physical device

---

## Configuration Parameters

All tuning parameters are in `picker/run_picker.py`:

```python
# Rotation threshold (finer control)
rotation_threshold = 2  # Detents per menu item (lower = more sensitive)

# Directional momentum filtering
rotation_history = []
history_window = 10      # Number of events to track
momentum_threshold = 3   # abs(sum) ≥ this = strong momentum
momentum_lookback = 5    # How many recent events to sum for momentum
```

**Encoder debounce** in `picker/rotary_encoder.py`:

```python
self._quad_required_reads = 2  # Stable CLK reads required (low latency)
```

**Button debounce** (separate, time-based):
```python
--rotary-debounce-ms 50  # Default 50ms button debounce
```

---

## Performance Characteristics

### Before Optimization:
- Menu update: ~1000ms (1 second per item)
- Full-screen flash: Yes (GC16 mode)
- Event lag: Yes (queue backup)
- Fast rotation: Ignored or reversed
- Wrap-around: Yes (confusing)
- Sensitivity: 1:1 (too touchy)

### After Optimization:
- Menu update: ~100-200ms (5-10x faster)
- Full-screen flash: No (partial refresh)
- Event lag: No (queue draining)
- Fast rotation: Fully responsive
- Wrap-around: No (sticks at ends)
- Sensitivity: 2:1 (fine control)
- Noise rejection: Intelligent (momentum-based)

---

## Hardware Compatibility

**Tested encoders**:
- Standard incremental rotary encoders with quadrature outputs (CLK/DT)
- Works with mechanical detents (most common)
- Should work with optical encoders (cleaner signal, less noise)

**Debounce requirements by encoder type**:
- **Clean optical encoders**: Can reduce to `_quad_required_reads = 1` for absolute minimum latency
- **Mechanical encoders** (typical): Current `_quad_required_reads = 2` is optimal
- **Noisy/cheap encoders**: May need `_quad_required_reads = 3` and adjust momentum thresholds

---

## Troubleshooting

### Menu jumps backward on fast rotation
- Momentum filter not aggressive enough
- Increase `momentum_threshold` (current: 3 → try 4 or 5)
- Increase `momentum_lookback` (current: 5 → try 7 or 10)

### Menu doesn't respond to fast rotation  
- Debounce too high
- Reduce `_quad_required_reads` (current: 2 → try 1, but may introduce noise)
- Check momentum filter isn't filtering legitimate events (review debug logs)

### Menu too sensitive (moves too fast)
- Increase `rotation_threshold` (current: 2 → try 3 or 4)

### Menu too sluggish (not responsive enough)
- Decrease `rotation_threshold` (current: 2 → try 1)

### Still seeing full-screen flashes
- Verify `prev_menu_image[0]` is being set properly
- Check logs for "mode: partial, has_prev: True"
- Ensure `update_waveshare/core.py` supports `prev_image_path` parameter

---

## Related Files

| File | Purpose |
|------|---------|
| `picker/rotary_encoder.py` | GPIO polling, quadrature decoding, debounce |
| `picker/run_picker.py` | Event loop, queue draining, momentum filter, threshold |
| `picker/rotary_core.py` | Navigation state machine (TOP_MENU/SUBMENU) |
| `picker/drivers/display_fast.py` | Display adapter, blit with prev_image_path |
| `picker/drivers/epaper_enhanced.py` | Waveshare wrapper, partial refresh support |
| `update_waveshare/core.py` | Differential bbox calculation, draw_partial |

---

## Design Principles

These optimizations follow key principles for responsive physical interfaces:

1. **Match user mental model**: Faster input = faster response (no artificial speed limits)
2. **Immediate feedback**: Display updates should complete before user's next action
3. **Natural feel**: Behavior should match physical mechanical devices
4. **Predictable boundaries**: No surprising wrap-around
5. **Appropriate sensitivity**: Require multiple detents for deliberate selection
6. **Intelligent filtering**: Reject noise without blocking legitimate input

---

## Future Enhancements

Potential improvements for specialized use cases:

1. **Acceleration curves**: Map rotation speed to menu movement multiplier (like mouse acceleration)
2. **Configurable threshold per menu**: Different menus could have different sensitivity
3. **Adaptive momentum filtering**: Automatically adjust thresholds based on recent noise patterns
4. **Multi-detent jump**: Hold button while rotating to move 5 items at a time
5. **Haptic feedback**: PWM buzzer on each menu item change (requires additional hardware)

---

## References

- **Quadrature Encoding**: https://en.wikipedia.org/wiki/Incremental_encoder
- **Gray Code**: https://en.wikipedia.org/wiki/Gray_code
- **Contact Debouncing**: https://www.ganssle.com/debouncing.htm
- **IT8951 E-Paper Controller**: Waveshare documentation
- **Partial Refresh Optimization**: E-paper display controller application notes

---

## Revision History

| Date | Change |
|------|--------|
| 2026-02-21 | Initial implementation of all optimizations |
| 2026-02-21 | Added directional momentum filtering |
| 2026-02-21 | Finalized parameters: threshold=2, debounce=2 reads, momentum window=10 |
