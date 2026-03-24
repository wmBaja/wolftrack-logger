#!/usr/bin/env python3
"""
Simple CAN Message Replay from Log File

A minimal script to replay CAN messages from a log file.
This is a simplified version for quick use.

Requirements:
    pip install "python-can"
"""

import can

def replay_log_simple(log_file, interface="virtual", channel="vcan0"):
    """
    Simple replay of CAN messages from log file.
    
    Args:
        log_file: Path to the log file
        interface: CAN interface type (e.g., 'socketcan', 'virtual', 'pcan')
        channel: CAN channel (e.g., 'can0', 'vcan0', 'PCAN_USBBUS1')
    """
    
    print(f"Replaying: {log_file}")
    print(f"Interface: {interface}, Channel: {channel}")
    
    # Open CAN bus
    with can.Bus(interface=interface, channel=channel) as bus:
        # Open log file
        with can.LogReader(log_file) as reader:
            # Replay with original timing
            for msg in can.MessageSync(reader):
                bus.send(msg)
                print(f"ID: 0x{msg.arbitration_id:03X}, Data: {msg.data.hex()}")
    
    print("Replay complete!")


# Example usage
if __name__ == "__main__":
    # Replace with your file path and interface
    LOG_FILE = "./tests/canEdge-GPS-Sample.blf"
    INTERFACE = "kvaser"  # Change to your interface: 'socketcan', 'pcan', 'vector', etc.
    CHANNEL = 0      # Change to your channel: 'can0', 'PCAN_USBBUS1', etc.
    
    replay_log_simple(LOG_FILE, INTERFACE, CHANNEL)