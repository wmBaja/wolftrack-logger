#!/bin/bash
# Switches the Raspberry Pi from Access Point mode back to Client mode.

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run with sudo"
  exit 1
fi

echo "Stopping Wolftrack Access Point..."
nmcli connection down Wolftrack 2>/dev/null || true

if [ -n "$1" ]; then
    SSID="$1"
    PASSWORD="$2"
    if [ -n "$PASSWORD" ]; then
        echo "Connecting to new network: $SSID..."
        nmcli device wifi connect "$SSID" password "$PASSWORD"
    else
        echo "Connecting to saved network: $SSID..."
        nmcli connection up "$SSID" || nmcli device wifi connect "$SSID"
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "\nSuccess! Connected to $SSID."
    else
        echo -e "\nFailed to connect to $SSID."
    fi
else
    echo -e "\nAccess Point stopped. NetworkManager will now automatically attempt to connect to any previously saved Wi-Fi networks in range."
    echo "To connect to a specific network manually, run:"
    echo "  sudo ./switch_to_client.sh <SSID> [PASSWORD]"
fi
