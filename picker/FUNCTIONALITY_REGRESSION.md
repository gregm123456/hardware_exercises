# Functionality Regression During Rotary Encoder Optimization

**Date**: 2026-02-21  
**Context**: While debugging and optimizing rotary encoder performance and display refresh issues, core application functionality was removed from the systemd service configuration.

## ⚠️ CRITICAL: Missing Functionality

The following features were **removed** during rotary encoder debugging and need to be **restored**:

---

## 1. Live Camera Streaming (Port 8088)

### What Was Removed

**Original service configuration** (from screenshots):
```bash
ExecStart=/home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py \
  --verbose \
  --stream \
  --stream-port 8088 \
  --rotary
```

**Current service configuration**:
```bash
ExecStart=/home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py \
  --rotary \
  --display-w 1448 \
  --display-h 1072
```

### Impact

**LOST FUNCTIONALITY**:
- ❌ No live MJPEG camera stream
- ❌ No web interface on `http://<PI_IP>:8088/stream.mjpg`
- ❌ No real-time monitoring of camera view
- ❌ Cannot preview camera framing before pressing "Go"

**PURPOSE OF THIS FEATURE**:
The live stream is a **core feature** that allows:
1. Remote monitoring of what the camera sees
2. Adjusting camera position/framing without touching the device
3. Web-based interface for observation during operation
4. Debugging camera issues remotely

---

## 2. Image-to-Image Generation Mode

### What Was Removed

**Original service** was using `picker_camera_still_startup.service` which included:
- Camera capture on "Go" button press
- img2img mode (not just txt2img)
- Integration with Stable Diffusion for image-based generation

**Current behavior**:
- Missing `--generation-mode img2img` flag
- "Go" button only shows "GO!" message and returns to menu
- No camera capture
- No image generation at all

### Impact

**LOST FUNCTIONALITY**:
- ❌ No camera snapshot capture when pressing "Go"
- ❌ No image-to-image generation with Stable Diffusion
- ❌ No structured interrogation of captured images
- ❌ No interrogation of generated images
- ❌ "Go" button effectively does nothing useful

**PURPOSE OF THIS FEATURE**:
This is the **PRIMARY PURPOSE** of the entire application:
1. User selects demographic categories via knobs/rotary encoder
2. User presses "Go"
3. Camera captures still image
4. Image is interrogated for demographic features (structured interrogation)
5. Image is sent to Stable Diffusion with selected prompts for img2img generation
6. Generated image is displayed on e-paper
7. Generated image is also interrogated

---

## 3. Verbose Logging

### What Was Removed

**Original**: `--verbose` flag enabled debug-level logging

**Current**: Standard INFO-level logging only

### Impact

**LOST FUNCTIONALITY**:
- ❌ Reduced diagnostic information
- ❌ Harder to debug issues
- ❌ Less visibility into SD client operations

---

## 4. Display Dimensions Configuration

### What Changed

**Original service**: Used hardcoded display size in code or different flags

**Current service**: Explicitly sets `--display-w 1448 --display-h 1072`

### Impact

**NEUTRAL**: This is actually an improvement - explicit configuration is better than implicit defaults. This should be **kept**.

---

## Original vs Current Feature Matrix

| Feature | Original (ADC Mode) | Original (Rotary - Working) | Current (Rotary - Broken) | Status |
|---------|---------------------|----------------------------|---------------------------|--------|
| Input Interface | 6 knobs + 2 buttons | Rotary encoder | Rotary encoder | ✅ Working |
| Display | E-paper 1448×1072 | E-paper 1448×1072 | E-paper 1448×1072 | ✅ Working |
| Partial Refresh | Implemented | Implemented | ✅ Implemented & Optimized | ✅ Working |
| Live Camera Stream | ✅ Port 8088 | ✅ Port 8088 | ❌ **REMOVED** | ❌ **BROKEN** |
| MJPEG Web Interface | ✅ Yes | ✅ Yes | ❌ **REMOVED** | ❌ **BROKEN** |
| Camera Snapshot | ✅ On "Go" press | ✅ On "Go" press | ❌ **REMOVED** | ❌ **BROKEN** |
| img2img Generation | ✅ Yes | ✅ Yes | ❌ **REMOVED** | ❌ **BROKEN** |
| SD Integration | ✅ txt2img + img2img | ✅ txt2img + img2img | ❌ **REMOVED** | ❌ **BROKEN** |
| Image Interrogation | ✅ Structured | ✅ Structured | ❌ **REMOVED** | ❌ **BROKEN** |
| Verbose Logging | ✅ Yes | ✅ Yes | ❌ **REMOVED** | ❌ **BROKEN** |
| Rotation Optimizations | N/A | ❌ Laggy/Flashing | ✅ Optimized | ✅ **NEW** |

---

## Code-Level Regression

### Service File Comparison

**ORIGINAL** (`picker_camera_still_startup.service` - from screenshot):
```ini
[Unit]
Description=Picker Rotary Encoder Service with Camera (img2img)
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=gregm
WorkingDirectory=/home/gregm/hardware_exercises
Environment=PYTHONPATH=/home/gregm/hardware_exercises
ExecStart=/home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py --verbose --stream --stream-port 8088 --rotary
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**CURRENT** (`picker_startup.service` - deployed):
```ini
[Unit]
Description=Picker Rotary Encoder Service with Camera (img2img)
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=gregm
WorkingDirectory=/home/gregm/hardware_exercises
Environment=PYTHONPATH=/home/gregm/hardware_exercises
ExecStart=/home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py --rotary --display-w 1448 --display-h 1072
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**DELTA**:
```diff
- ExecStart=... --verbose --stream --stream-port 8088 --rotary
+ ExecStart=... --rotary --display-w 1448 --display-h 1072
```

### Missing Action Handler Implementation

**CURRENT CODE** in `picker/run_picker.py` (`_do_action` function):
```python
def _do_action(action_name):
    """Handle Go / Reset actions."""
    logger.info(f"Action triggered: {action_name}")
    try:
        msg = "GO!" if action_name == "Go" else "RESETTING"
        img = compose_message(msg, full_screen=effective_size)
        # Use full mode for action message (important status change)
        blit(img, action_name.lower(), rotate, "full")
        time.sleep(2.0)
        # Return to menu instead of staying stuck on action message
        title, items, idx = core.current_display()
        _do_display(title, items, idx)
    except Exception as exc:
        logger.debug(f"Action display failed: {exc}")
```

**WHAT'S MISSING**: No integration with:
- Camera capture (`capture_still.py`)
- SD client (`sd_client.py`)
- Structured interrogation
- Image generation workflow

**ORIGINAL ADC MODE** had this in `picker/core.py` with full camera/SD integration.

---

## Root Cause Analysis

### How This Happened

1. **Initial Problem**: Rotary encoder had performance issues (lag, flashing, wrapping, sensitivity)
2. **Debugging Focus**: Effort concentrated on:
   - Display refresh optimization
   - Event queue draining
   - Directional momentum filtering
   - Encoder debouncing
3. **Service File Simplification**: To isolate rotary encoder issues, service was simplified to minimal flags
4. **Tunnel Vision**: Optimization work succeeded but lost sight of original application purpose
5. **No Integration Testing**: Rotary encoder works perfectly, but application no longer does what it was designed for

---

## What Still Works

✅ **Fully Functional**:
- Rotary encoder hardware polling (GPIO)
- Quadrature decoding with noise rejection
- Menu navigation (TOP_MENU ↔ SUBMENU)
- Button press detection
- E-paper partial refresh (fast, no flashing)
- Display brightness (proper orientation)
- Menu wrapping disabled (sticks at ends)
- Rotation threshold (2 detents = 1 item)
- Directional momentum filtering
- Event queue draining (immediate stop)

✅ **Code Exists But Not Invoked**:
- Camera manager (`picker/capture_still.py`)
- SD client (`picker/sd_client.py`)
- Image interrogation (`sd_client.interrogate_structured()`)
- Structured categories for interrogation
- MJPEG streaming server
- Image display on e-paper

---

## Recovery Path (NOT TO BE EXECUTED NOW)

When ready to restore full functionality:

### Step 1: Restore Service Flags
```bash
# Edit /etc/systemd/system/picker_startup.service
ExecStart=/home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py \
  --rotary \
  --display-w 1448 \
  --display-h 1072 \
  --generation-mode img2img \
  --stream \
  --stream-port 8088 \
  --verbose
```

### Step 2: Implement Camera/SD Integration in Rotary Mode

The `_do_action()` function in `picker/run_picker.py` needs to be enhanced to:
1. Capture camera still when "Go" is pressed
2. Perform structured interrogation of captured image
3. Build prompt from selected menu values
4. Send to Stable Diffusion for img2img generation
5. Display generated image on e-paper
6. Interrogate generated image

**Reference Implementation**: `picker/core.py` lines ~380-470 (ADC mode has full implementation)

### Step 3: Initialize Camera Manager in Rotary Mode

Add to `_run_rotary()` function initialization:
```python
# Initialize camera manager for img2img mode
if args.stream:
    from picker.capture_still import CameraManager
    camera_manager = CameraManager(
        stream=args.stream,
        stream_port=args.stream_port
    )
    logger.info(f"Camera stream available at http://<IP>:{args.stream_port}/stream.mjpg")
```

### Step 4: Testing Checklist

Before considering recovery complete:
- [ ] Live stream accessible on port 8088
- [ ] "Go" button captures camera snapshot
- [ ] Structured interrogation runs on captured image
- [ ] Prompt built from selected menu values
- [ ] img2img generation completes
- [ ] Generated image displays on e-paper
- [ ] Generated image is interrogated
- [ ] Results logged properly
- [ ] Display still uses partial refresh (no regression)
- [ ] Rotary encoder still responsive (no regression)

---

## Priority Assessment

### Critical (Application Unusable Without)
1. **Camera streaming** - Core monitoring feature
2. **img2img generation** - Core application purpose
3. **"Go" button functionality** - Currently does nothing useful

### Important (Degrades Experience)
4. **Verbose logging** - Helpful for debugging
5. **Structured interrogation** - Validates generation quality

### Nice to Have (No Impact on Core Function)
6. Display dimensions (already handled explicitly - keep as is)

---

## Lessons Learned

1. **Feature Branches**: Performance optimization should have been done in a branch with integration testing before deployment
2. **Integration Tests**: Need automated tests that verify end-to-end workflow, not just component behavior
3. **Service Configuration Management**: Service files should be version-controlled with comments explaining each flag
4. **Regression Testing**: Checklist of core features to verify after any significant change
5. **Documentation First**: This regression doc should have been created BEFORE stripping features

---

## Current System State

**What's Running**:
```bash
sudo systemctl status picker_startup.service
# Active: running with just rotary encoder + display
# Missing: camera, streaming, SD generation
```

**What Works**:
- ✅ Rotary encoder navigation (optimized, responsive, no lag)
- ✅ E-paper display (partial refresh, fast, no flashing)
- ✅ Menu selection persistence
- ✅ Button press detection

**What's Broken**:
- ❌ Live camera stream (port 8088 not listening)
- ❌ "Go" button (shows message, doesn't generate)
- ❌ img2img workflow (not invoked)
- ❌ Camera capture (not initialized)
- ❌ SD API calls (not executed)

---

## References

- Original ADC implementation: `picker/core.py` (lines 350-500)
- Camera manager: `picker/capture_still.py`
- SD client: `picker/sd_client.py`
- Service README: `picker/README_picker_startup.md`
- Optimization guide: `picker/ROTARY_ENCODER_OPTIMIZATION.md`

---

## Sign-Off

**Status**: DOCUMENTED, NOT FIXED  
**Next Action**: When ready to restore functionality, use this document as the restoration roadmap  
**Preserved**: All optimizations from rotary encoder work must be maintained during restoration  

The rotary encoder now provides an excellent, responsive user experience. The challenge is to integrate it with the original camera/SD workflow without losing the performance gains.
