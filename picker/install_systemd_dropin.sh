#!/bin/bash
# Install systemd drop-in to ensure tmpfiles are processed before picker service
# Run with sudo

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo ./picker/install_systemd_dropin.sh"
  exit 1
fi

mkdir -p /etc/systemd/system/picker_camera_still_startup.service.d
cp -f "$(pwd)/picker/systemd/tmpfiles.conf" /etc/systemd/system/picker_camera_still_startup.service.d/tmpfiles.conf
systemctl daemon-reload
echo "Installed drop-in and reloaded systemd. Restarting service..."
systemctl restart picker_camera_still_startup.service || true
systemctl status picker_camera_still_startup.service --no-pager || true

echo "Done. The drop-in ensures systemd runs tmpfiles before the picker service starts."
