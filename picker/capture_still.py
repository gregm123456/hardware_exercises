#!/usr/bin/env python3

import time
import io
import threading
import logging
import errno
from http.server import HTTPServer, BaseHTTPRequestHandler
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from PIL import Image

logger = logging.getLogger(__name__)

class StreamingOutput(io.BufferedIOBase):
    """Thread-safe buffer for MJPEG frames that satisfies BufferedIOBase interface."""
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)  # Return number of bytes written
    
    def writable(self):
        return True

class StreamingHandler(BaseHTTPRequestHandler):
    """HTTP handler for MJPEG streaming."""
    def do_GET(self):
        if self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    with self.server.output.condition:
                        self.server.output.condition.wait()
                        frame = self.server.output.frame
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logger.debug(f"Streaming client disconnected: {e}")
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(HTTPServer):
    allow_reuse_address = True


class CameraManager:
    def __init__(self, stream=False, port=8088):
        self.server = None
        self.server_thread = None
        self.stream_port = None
        self.output = None

        try:
            self.picam2 = Picamera2()

            # Get sensor pixel array size for calculating crop
            sensor_size = self.picam2.camera_properties.get('PixelArraySize', (1920, 1080))
            sensor_w, sensor_h = sensor_size
            logger.info(f"Detected sensor size: {sensor_w}x{sensor_h}")

            # Calculate hardware crop for centered square (full height)
            side = min(sensor_w, sensor_h)
            x = (sensor_w - side) // 2
            y = (sensor_h - side) // 2
            # Libcamera ScalerCrop is (x, y, width, height)
            self.crop = (x, y, side, side)
            logger.info(f"Calculated centered square crop: {self.crop}")

            # Create configuration. We use 'main' for high-res RGB and 'lores' for YUV/MJPEG.
            config = self.picam2.create_video_configuration(
                main={'format': 'RGB888', 'size': (512, 512)},
                lores={'format': 'YUV420', 'size': (512, 512)},
                encode='lores',
                buffer_count=6
            )

            # picamera2 allows setting scaler_crop on the stream config
            config['main']['scaler_crop'] = self.crop
            config['lores']['scaler_crop'] = self.crop

            # Configure and start
            self.picam2.configure(config)
            self.picam2.start()
            logger.info("Camera started with dual streams (main+lores)")

            if stream:
                self.output = StreamingOutput()
                # Use start_recording with an encoder. Since we set encode='lores'
                # in the config, it will pull from the lores stream.
                self.picam2.start_recording(
                    MJPEGEncoder(),
                    FileOutput(self.output)
                )

                self.server, bound_port = self._bind_streaming_server(port)
                self.stream_port = bound_port
                self.server.output = self.output
                self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.server_thread.start()
                if bound_port != port:
                    logger.warning(f"Port {port} was busy; MJPEG stream moved to port {bound_port}")
                else:
                    logger.info(f"MJPEG stream server started on port {bound_port}")

            # Initial warm-up
            time.sleep(1)
        except Exception as e:
            logger.exception(f"CameraManager failed to initialize: {e}")
            raise

    def _bind_streaming_server(self, preferred_port, retries=10):
        last_error = None
        for offset in range(retries):
            candidate = preferred_port + offset
            try:
                server = StreamingServer(('', candidate), StreamingHandler)
                return server, candidate
            except OSError as err:
                if err.errno == errno.EADDRINUSE:
                    logger.warning(f"Port {candidate} already in use; trying next port")
                    last_error = err
                    continue
                raise
        raise last_error if last_error else OSError(errno.EADDRINUSE, "No ports available for MJPEG stream")

    def capture_still(self):
        """Capture a 512x512 RGB frame from the hardware-cropped 'main' stream."""
        if not self.picam2:
            raise RuntimeError("Camera not initialized")
        
        # capture_array() pulled from the 'main' stream (which is scaled to 512x512)
        try:
            logger.debug("Executing capture_array on 'main' stream...")
            # Picamera2.capture_array uses 'name' as the first positional argument
            # for the stream name, rather than a 'stream' keyword.
            image_array = self.picam2.capture_array('main')
            # Some camera backends return arrays in BGR channel order even when
            # configured for RGB; ensure we present a proper RGB PIL image by
            # swapping channels if necessary. Swapping unconditionally is
            # inexpensive and keeps colors consistent with the MJPEG stream.
            try:
                # Log the first pixel for quick diagnostics (dtype safe)
                if image_array.ndim == 3 and image_array.shape[2] >= 3:
                    logger.debug(f"Captured first pixel (raw): {image_array[0,0,:3].tolist()}")
                rgb_array = image_array[..., ::-1]
            except Exception:
                # Fall back to using the original array if something unexpected
                # is returned by the camera (e.g., single-channel arrays).
                logger.debug("Could not swap channels; using captured array as-is")
                rgb_array = image_array

            image = Image.fromarray(rgb_array)
            logger.info(f"Successfully captured {image.size} image from camera")
            return image
        except Exception as e:
            logger.error(f"Failed to capture array from main stream: {e}")
            raise

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                logger.debug("Error shutting down streaming server", exc_info=True)
            self.server = None
        if self.picam2:
            try:
                self.picam2.stop_recording()
            except Exception:
                pass
            self.picam2.stop()

def capture_and_process():
    # Simple standalone test
    cm = CameraManager(stream=True, port=8000)
    try:
        print("Camera started. Stream at http://localhost:8000/stream.mjpg")
        print("Waiting 5 seconds for preview...")
        time.sleep(5)
        
        image = cm.capture_still()
        image.save("still.png")
        print("Captured still.png (512x512, hardware cropped)")
    finally:
        cm.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    capture_and_process()
