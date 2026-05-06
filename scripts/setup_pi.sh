#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Wolftrack Logger Raspberry Pi Setup ===${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run this script with sudo or as root${NC}"
  exit 1
fi

# 1. System Dependencies
echo -e "\n${BLUE}[1/6] Installing system dependencies...${NC}"
apt-get update
apt-get install -y curl git i2c-tools can-utils network-manager swig libgpiod-dev liblgpio-dev python3-dev

# 2. Python Setup via uv
echo -e "\n${BLUE}[2/6] Setting up Python environment...${NC}"
# Install uv for the user who invoked sudo, not root (unless root invoked)
SUDO_USER=${SUDO_USER:-root}
USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)

if ! sudo -u "$SUDO_USER" command -v uv &> /dev/null; then
    echo "Installing uv..."
    sudo -u "$SUDO_USER" bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

# Make sure uv is in PATH for this session
export PATH="$USER_HOME/.local/bin:$PATH"

# Run uv sync
echo "Syncing dependencies with uv..."
# Run as the regular user to avoid creating root-owned files in the project
sudo -u "$SUDO_USER" bash -c "export PATH=\"$USER_HOME/.local/bin:\$PATH\" && cd \"$(pwd)\" && uv sync"

# 3. Environment Variables
echo -e "\n${BLUE}[3/6] Configuring environment variables...${NC}"
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    sudo -u "$SUDO_USER" cp .env.example .env
else
    echo ".env file already exists. Skipping."
fi

# 4. Boot Overlays (CAN & RTC)
echo -e "\n${BLUE}[4/6] Configuring boot overlays...${NC}"
CONFIG_TXT="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_TXT" ]; then
    # Fallback for older systems
    CONFIG_TXT="/boot/config.txt"
fi

echo "Checking $CONFIG_TXT for CAN and RTC overlays..."

# CAN Overlay
if ! grep -q "dtoverlay=mcp251xfd" "$CONFIG_TXT"; then
    echo "Adding Waveshare CAN FD HAT overlays..."
    cat << EOF >> "$CONFIG_TXT"

# Waveshare 2-CH CAN FD HAT
dtparam=spi=on
dtoverlay=spi1-3cs
dtoverlay=mcp251xfd,spi0-0,interrupt=25
dtoverlay=mcp251xfd,spi1-0,interrupt=24
EOF
fi

# RTC Overlay
if ! grep -q "dtoverlay=i2c-rtc,ds3231" "$CONFIG_TXT"; then
    echo "Adding DS3231 RTC overlay..."
    cat << EOF >> "$CONFIG_TXT"

# Adafruit DS3231 RTC
dtparam=i2c_arm=on
dtoverlay=i2c-rtc,ds3231
EOF
fi

# 5. Systemd Services
echo -e "\n${BLUE}[5/6] Setting up Systemd Services...${NC}"

# CAN Interface Setup Service
echo "Installing CAN network setup service..."
chmod +x scripts/bring_can_up.sh
sed -e "s|{{WORKING_DIR}}|$(pwd)|g" \
    scripts/can0-setup.service.template > /etc/systemd/system/can0-setup.service
systemctl daemon-reload
systemctl enable can0-setup.service

# Wolftrack Logger App Service
echo "Installing Wolftrack Logger service..."
sed -e "s|{{WORKING_DIR}}|$(pwd)|g" \
    -e "s|{{USER}}|$SUDO_USER|g" \
    scripts/wolftrack-logger.service.template > /etc/systemd/system/wolftrack-logger.service

systemctl daemon-reload
systemctl enable wolftrack-logger.service

# 6. Access Point Setup
echo -e "\n${BLUE}[6/6] Configuring Wi-Fi Access Point...${NC}"
echo "Setting up 'Wolftrack' open Access Point using NetworkManager..."

# Delete existing connection with same name if it exists to avoid duplicates
nmcli connection delete Wolftrack 2>/dev/null || true
nmcli connection delete Hotspot 2>/dev/null || true

# Create connection profile
nmcli con add type wifi ifname wlan0 con-name Wolftrack autoconnect yes ssid Wolftrack

# Configure as an Access Point (shared connection, no security)
nmcli con modify Wolftrack 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared

# Bring up the interface
nmcli con up Wolftrack

echo -e "\n${GREEN}=== Setup Complete! ===${NC}"
echo -e "The Raspberry Pi must be rebooted to apply boot overlays and start the Access Point."
echo -e "Rebooting in 10 seconds... (Press Ctrl+C to cancel)"
sleep 10
reboot
