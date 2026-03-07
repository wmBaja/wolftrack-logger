#!/usr/bin/env python3
"""
Simple CAN Message Replay from MF4 File

A minimal script to replay CAN messages from an MF4 file.
This is a simplified version for quick use.

Requirements:
    pip install python-can[mf4]
"""

import can

def replay_mf4_simple(mf4_file, interface="virtual", channel="vcan0"):
    """
    Simple replay of CAN messages from MF4 file.
    
    Args:
        mf4_file: Path to the MF4 file
        interface: CAN interface type (e.g., 'socketcan', 'virtual', 'pcan')
        channel: CAN channel (e.g., 'can0', 'vcan0', 'PCAN_USBBUS1')
    """
    
    print(f"Replaying: {mf4_file}")
    print(f"Interface: {interface}, Channel: {channel}")
    
    # Open CAN bus
    with can.Bus(interface=interface, channel=channel) as bus:
        # Open MF4 file
        with can.MF4Reader(mf4_file) as reader:
            # Replay with original timing
            for msg in can.MessageSync(reader):
                bus.send(msg)
                print(f"ID: 0x{msg.arbitration_id:03X}, Data: {msg.data.hex()}")
    
    print("Replay complete!")


# Example usage
if __name__ == "__main__":
    # Replace with your file path and interface
    MF4_FILE = "./tests/canEdge-GPS-Sample.mf4"
    INTERFACE = "kvaser"  # Change to your interface: 'socketcan', 'pcan', 'vector', etc.
    CHANNEL = 0      # Change to your channel: 'can0', 'PCAN_USBBUS1', etc.
    
    replay_mf4_simple(MF4_FILE, INTERFACE, CHANNEL)