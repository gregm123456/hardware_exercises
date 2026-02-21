# Picker Startup Service

This directory contains the systemd service file for running the picker application as a startup service.

## Files

- `picker_startup.service`: Systemd service configuration file

## Installation

To install the picker as a systemd service:

1. Copy the service file to the systemd directory:
   ```
   sudo cp picker_startup.service /etc/systemd/system/
   ```

2. Reload systemd to recognize the new service:
   ```
   sudo systemctl daemon-reload
   ```

3. Enable the service to start on boot:
   ```
   sudo systemctl enable picker_startup
   ```

4. Start the service immediately (optional, it will start on next boot):
   ```
   sudo systemctl start picker_startup
   ```

## Service Management

Check the status of the service:
```
sudo systemctl status picker_startup
```

View logs:
```
sudo journalctl -u picker_startup -f
```

Stop the service:
```
sudo systemctl stop picker_startup
```

Disable the service (prevent auto-start on boot):
```
sudo systemctl disable picker_startup
```

## Configuration

The service runs the picker with the following settings:
- User: gregm
- Working Directory: /home/gregm/hardware_exercises
- PYTHONPATH: /home/gregm/hardware_exercises:$PYTHONPATH
- Command: /home/gregm/hardware_exercises/.venv/bin/python3 picker/run_picker.py --verbose --stream --stream-port 8088 --rotary
- Restart: always (automatically restarts on failure)

### Switching Input Interfaces (Rotary vs. Knobs)

By default, the service is configured to use the **single rotary encoder** interface via the `--rotary` flag. If you wish to switch to the **six-knob (ADC)** interface:

1. Edit the service file:
   ```bash
   sudo nano /etc/systemd/system/picker_startup.service
   ```
2. In the `ExecStart` line, remove the `--rotary` flag to use the knobs (MCP3008), or add it to use the encoder.
3. Reload systemd and restart the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart picker_startup
   ```

## Notes

- Ensure the virtual environment at `/home/gregm/hardware_exercises/.venv` is properly set up
- The service assumes the hardware (SPI devices, etc.) is available at startup
- Check system logs if the service fails to start due to hardware issues