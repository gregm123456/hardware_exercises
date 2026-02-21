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
```bash
sudo systemctl status picker_camera_still_startup
```

View logs:
```bash
sudo journalctl -u picker_camera_still_startup -f
```

Stop the service:
```bash
sudo systemctl stop picker_camera_still_startup
```

Disable the service (prevent auto-start on boot):
```bash
sudo systemctl disable picker_camera_still_startup
```

## Configuration

### Image Generation Tuning
The img2img generation behavior can be tuned in `picker/sd_config.py`. Key parameters include:

- `SD_DENOISING_STRENGTH`: Controls how much the generated image deviates from the captured camera still. A value of `0.5` (default) provides a balance between following the original structure and applying the prompt.
- `SD_STEPS`, `SD_CFG_SCALE`: Standard Stable Diffusion generation parameters.
- `EPAPER_GAMMA`: Adjusts the brightness of the generated image for better visibility on e-paper displays.

### Service Settings
The service runs the picker with the following settings:
- User: gregm
- Working Directory: /home/gregm/hardware_exercises
- PYTHONPATH: /home/gregm/hardware_exercises:$PYTHONPATH
- Command: /home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py --generation-mode img2img --verbose --rotary
- Restart: always (automatically restarts on failure)

### Switching Input Interfaces (Rotary vs. Knobs)

By default, the service is configured to use the **single rotary encoder** interface via the `--rotary` flag. If you wish to switch to the **six-knob (ADC)** interface:

1. Edit the service file:
   ```bash
   sudo nano /etc/systemd/system/picker_camera_still_startup.service
   ```
2. In the `ExecStart` line, remove the `--rotary` flag to use the knobs, or add it to use the encoder.
3. Reload systemd and restart the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart picker_camera_still_startup
   ```

## Notes

### Raspberry Pi 5 Special Requirements
If running on a Raspberry Pi 5, the following additional steps are required for the camera and display to function:

1. **Venv Creation**: The virtual environment must be created with `--system-site-packages` to allow access to the system-level `libcamera` and Pi 5-compatible `RPi.GPIO` packages.
   ```bash
   python -m venv .venv --system-site-packages
   ```
2. **Camera Tuning**: Arducam modules require a tuning file to be present. Use the provided setup script:
   ```bash
   ./setup_camera_tuning.sh
   # And ensure the tmpfiles config is installed
   sudo cp picker/systemd/tmpfiles.conf /etc/tmpfiles.d/arducam.conf
   sudo systemd-tmpfiles --create /etc/tmpfiles.d/arducam.conf
   ```
3. **Infinite Restart Policy**: The provided service file is configured to restart indefinitely (`StartLimitIntervalSec=0`). This is necessary on Pi 5 to handle race conditions during boot-time hardware initialization.

- Ensure the virtual environment at `/home/gregm/hardware_exercises/.venv` is properly set up
- The service assumes the hardware (SPI devices, camera, etc.) is available at startup
- Check system logs if the service fails to start due to hardware issues
- If camera capture fails, the service falls back to txt2img mode for that generation