# Live MJPEG Camera Streaming Plan

Implement a parallel MJPEG streaming service for the `picker` project using `picamera2` dual-stream capabilities.

## Goals
- Provide a persistent 512x512 MJPEG stream over HTTP (port 8000 by default).
- Ensure high-resolution (512x512) still captures are instant and do not interrupt the stream.
- Use hardware-level ISP cropping (`scaler_crop`) to achieve a centered 1:1 aspect ratio at 512x512 resolution.
- Minimal CPU overhead by offloading scaling and cropping to the Pi's ISP.

## Implementation Details

### 1. `picker/capture_still.py` Refactor
- **`StreamingOutput` Class**: A thread-safe buffer that holds the latest MJPEG frame and uses a `threading.Condition` to notify waiting HTTP clients.
- **`StreamingHandler` Class**: A `BaseHTTPRequestHandler` that serves the MJPEG stream using the `multipart/x-mixed-replace` content type.
- **`CameraManager` Updates**:
    - Initialize `picamera2` with two streams:
        - `main`: RGB888, 512x512 (used for `capture_array`).
        - `video`: MJPEG, 512x512 (used for streaming).
    - Calculate `scaler_crop` based on sensor dimensions to take a centered square of the full sensor height.
    - Start an `http.server.HTTPServer` in a background daemon thread.
    - Start recording the `video` stream into the `StreamingOutput` using `MJPEGEncoder`.
    - `capture_still()`: Directly pull from the `main` stream's raw buffer; no software resizing/cropping needed.

### 2. `picker/core.py` Integration
- Accept `stream` (bool) and `stream_port` (int) in `PickerCore.__init__`.
- Pass these parameters to `CameraManager`.

### 3. `picker/run_picker.py` CLI Updates
- Add `--stream` flag to enable the live view.
- Add `--stream-port` (default 8000) argument.
- Log the streaming URL (e.g., `http://<LOCAL_IP>:<PORT>/stream.mjpg`) to the console on startup.

### 4. HTML Preview
- Create `picker/stream_preview.html` with a base snippet for embedding the 512x512 stream.

## HTML Embedding Snippet
```html
<div class="camera-preview">
    <h3>Live Stream (512x512 Square)</h3>
    <img src="http://<IP_ADDRESS>:8000/stream.mjpg" width="512" height="512">
</div>
```
