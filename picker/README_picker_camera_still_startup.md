# Picker Camera Still Startup Service

This directory contains the systemd service file for running the picker application in img2img mode as a startup service. In this mode, pressing the GO button captures a camera image and uses it as the base for image generation via img2img.

## Files

- `picker_camera_still_startup.service`: Systemd service configuration file

## Installation

To install the picker camera still service as a systemd service:

1. Copy the service file to the systemd directory:
   ```
   sudo cp picker_camera_still_startup.service /etc/systemd/system/
   ```

2. Reload systemd to recognize the new service:
   ```
   sudo systemctl daemon-reload
   ```

3. Enable the service to start on boot:
   ```
   sudo systemctl enable picker_camera_still_startup
   ```

4. Start the service immediately (optional, it will start on next boot):
   ```
   sudo systemctl start picker_camera_still_startup
   ```

## Service Management

Check the status of the service:
```
sudo systemctl status picker_camera_still_startup
```

View logs:
```
sudo journalctl -u picker_camera_still_startup -f
```

Stop the service:
```
sudo systemctl stop picker_camera_still_startup
```

Disable the service (prevent auto-start on boot):
```
sudo systemctl disable picker_camera_still_startup
```

## Configuration

The service runs the picker with the following settings:
- User: gregm
- Working Directory: /home/gregm/hardware_exercises
- PYTHONPATH: /home/gregm/hardware_exercises:$PYTHONPATH
- Command: /home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py --generation-mode img2img --verbose
- Restart: always (automatically restarts on failure)

## Notes

- Ensure the virtual environment at `/home/gregm/hardware_exercises/.venv` is properly set up
- The service assumes the hardware (SPI devices, camera, etc.) is available at startup
- Check system logs if the service fails to start due to hardware issues
- If camera capture fails, the service falls back to txt2img mode for that generation