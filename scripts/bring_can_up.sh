#!/bin/bash
# Sources the .env file and configures the CAN interfaces accordingly

# Find the project root (parent of the scripts directory)
WORKING_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
ENV_FILE="$WORKING_DIR/.env"

# Default values
BITRATE=1000000
FD_ON=false
DBITRATE=2000000

if [ -f "$ENV_FILE" ]; then
    # Source .env, ignoring comments and empty lines
    set -a
    source <(grep -v '^[[:space:]]*#' "$ENV_FILE" | grep -v '^[[:space:]]*$')
    set +a
fi

# Override with environment variables if set
BITRATE=${CAN_BITRATE:-$BITRATE}
FD_ON=${CAN_FD:-$FD_ON}
DBITRATE=${CAN_DATA_BITRATE:-$DBITRATE}

setup_can() {
    local IFACE=$1
    
    # Check if interface exists before trying to configure
    if ! ip link show $IFACE > /dev/null 2>&1; then
        return 1
    fi

    # Bring interface down first to allow configuration changes
    ip link set $IFACE down 2>/dev/null || true
    
    # Configure bitrate and FD modes
    # Ensure variables are treated as lowercase strings for comparison
    if [ "${FD_ON,,}" = "true" ]; then
        ip link set $IFACE type can bitrate $BITRATE fd on dbitrate $DBITRATE
    else
        ip link set $IFACE type can bitrate $BITRATE
    fi
    
    # Bring interface up
    ip link set $IFACE up
}

echo "Configuring CAN interfaces (Bitrate: $BITRATE, FD: $FD_ON)..."

FOUND_IFACE=false

setup_can can0 && { echo "can0 configured successfully."; FOUND_IFACE=true; } || echo "can0 not found or failed to configure."
setup_can can1 && { echo "can1 configured successfully."; FOUND_IFACE=true; } || echo "can1 not found or failed to configure."

if [ "$FOUND_IFACE" = false ]; then
    echo "No physical CAN interface found. Falling back to virtual CAN (vcan0)..."
    
    # Load the vcan kernel module if not already loaded
    if ! lsmod | grep -q "^vcan"; then
        modprobe vcan || { echo "ERROR: Failed to load vcan module. Cannot set up virtual CAN."; exit 1; }
    fi
    
    # Create vcan0 if it doesn't already exist
    if ! ip link show vcan0 > /dev/null 2>&1; then
        ip link add dev vcan0 type vcan || { echo "ERROR: Failed to create vcan0."; exit 1; }
    fi
    
    ip link set vcan0 up && echo "vcan0 configured successfully (virtual CAN)." || { echo "ERROR: Failed to bring up vcan0."; exit 1; }
fi

exit 0
