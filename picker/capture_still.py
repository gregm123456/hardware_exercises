#!/usr/bin/env python3

import time
from picamera2 import Picamera2
from PIL import Image

def capture_and_process():
    # Initialize the camera
    picam2 = Picamera2()
    
    # Configure for still capture
    config = picam2.create_still_configuration()
    picam2.configure(config)
    
    # Start the camera
    picam2.start()
    
    # Allow some time for the camera to adjust
    time.sleep(2)
    
    # Capture the image as an array
    image_array = picam2.capture_array()
    
    # Stop the camera
    picam2.stop()
    
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
    # If already square, do nothing
    
    # Resize to 512x512
    image = image.resize((512, 512), Image.LANCZOS)
    
    # Save as still.png
    image.save("still.png")
    print("Image saved as still.png")

if __name__ == "__main__":
    capture_and_process()