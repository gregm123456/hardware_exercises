#!/usr/bin/env python3

import time
import io
from picamera2 import Picamera2
from PIL import Image

class CameraManager:
    def __init__(self):
        self.picam2 = Picamera2()
        self.config = self.picam2.create_still_configuration()
        self.picam2.configure(self.config)
        self.picam2.start()
        # Initial warm-up
        time.sleep(1)

    def capture_still(self):
        # Capture the image as an array
        image_array = self.picam2.capture_array()
        
        # Convert to PIL Image (assuming RGB format)
        image = Image.fromarray(image_array)
        
        # Get dimensions
        width, height = image.size
        
        # Crop to square: assume width >= height, crop left and right
        if width > height:
            left = (width - height) // 2
            right = left + height
            image = image.crop((left, 0, right, height))
        elif height > width:
            # If taller, crop top and bottom (though unlikely for cameras)
            top = (height - width) // 2
            bottom = top + width
            image = image.crop((0, top, width, bottom))
            
        # Resize to 512x512 for SD
        image = image.resize((512, 512), Image.Resampling.LANCZOS)
        return image

    def stop(self):
        self.picam2.stop()

def capture_and_process():
    cm = CameraManager()
    try:
        # Allow some extra time for the very first capture if run as standalone
        time.sleep(1)
        image = cm.capture_still()
        
        # Save to file
        image.save("still.png")
        print("Captured still.png")
    finally:
        cm.stop()

if __name__ == "__main__":
    capture_and_process()