#!/bin/bash
# Switches the Raspberry Pi from Client mode into Access Point mode.

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo"
  exit 1
fi

echo "Starting Wolftrack Access Point..."

# Disconnect active Wi-Fi to free up the wlan0 interface
nmcli device disconnect wlan0 2>/dev/null || true

# Bring up the AP profile created by setup_pi.sh
nmcli connection up Wolftrack

if [ $? -eq 0 ]; then
    echo -e "\nSuccess! The Pi is now broadcasting the 'Wolftrack' Wi-Fi network."
else
    echo -e "\nFailed to start the Access Point. Have you run the initial setup script yet to create the profile?"
fi
