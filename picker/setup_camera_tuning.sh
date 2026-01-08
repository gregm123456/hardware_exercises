#!/bin/bash
# Camera tuning file setup for Arducam Pivariety
# Run this as root or with sudo
# This script sets up the necessary camera tuning file symlink for img2img mode
# and makes it persistent across system updates

set -e  # Exit on any error

echo "Setting up camera tuning file for Arducam Pivariety..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo"
    exit 1
fi

# Create backup directory
mkdir -p /usr/local/share/libcamera/backup

# Backup the working tuning file
if [ -f /usr/share/libcamera/ipa/rpi/pisp/arducam_64mp.json ]; then
    cp -p /usr/share/libcamera/ipa/rpi/pisp/arducam_64mp.json /usr/local/share/libcamera/backup/arducam_64mp.json
    chown root:root /usr/local/share/libcamera/backup/arducam_64mp.json
    chmod 644 /usr/local/share/libcamera/backup/arducam_64mp.json
    echo "Backed up arducam_64mp.json to /usr/local/share/libcamera/backup/"
else
    echo "ERROR: Source tuning file /usr/share/libcamera/ipa/rpi/pisp/arducam_64mp.json not found"
    exit 1
fi

# Create the symlink
ln -sf /usr/local/share/libcamera/backup/arducam_64mp.json /usr/share/libcamera/ipa/rpi/pisp/arducam-pivariety.json
echo "Created symlink: arducam-pivariety.json -> arducam_64mp.json"

# Make it persistent across updates using systemd tmpfiles
echo "L /usr/share/libcamera/ipa/rpi/pisp/arducam-pivariety.json - - - - /usr/local/share/libcamera/backup/arducam_64mp.json" > /etc/tmpfiles.d/arducam-pivariety.conf
systemd-tmpfiles --create /etc/tmpfiles.d/arducam-pivariety.conf
echo "Made symlink persistent with systemd tmpfiles"

echo "Camera tuning setup complete!"
echo "The Arducam Pivariety camera should now work in img2img mode."
echo "You can verify with: ls -l /usr/share/libcamera/ipa/rpi/pisp/arducam-pivariety.json"