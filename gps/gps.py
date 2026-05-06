import serial, pynmea2, io, can, subprocess, os
from dotenv import load_dotenv, find_dotenv

# Automatically search for a .env file in the current directory or parent directories
load_dotenv(find_dotenv())

can_channel = os.getenv('CAN_CHANNEL', 'can0')
can_interface = os.getenv('CAN_INTERFACE', 'socketcan')
can_fd = os.getenv('CAN_FD', 'false').lower() == 'true'
is_extended_id = os.getenv('CAN_EXTENDED_ID', 'false').lower() == 'true'
bitrate_switch = os.getenv('CAN_BITRATE_SWITCH', str(can_fd)).lower() == 'true'

gps = serial.Serial(port="/dev/serial0", baudrate=115200, timeout=1)
sio = io.TextIOWrapper(io.BufferedRWPair(gps, gps))
bus = can.interface.Bus(channel=can_channel, interface=can_interface, fd=can_fd)

while True:
    try:
        line = sio.readline()
        if not line.strip():
            continue
        msg = pynmea2.parse(line)

        if not isinstance(msg, pynmea2.types.talker.RMC):
            continue

        print(repr(msg))

        if msg.status == 'A' and msg.lat != '':
            lat_raw = float(msg.lat)
            lon_raw = float(msg.lon)
            lat_deg = int(lat_raw / 100) + (lat_raw % 100) / 60
            lon_deg = int(lon_raw / 100) + (lon_raw % 100) / 60
            if msg.lat_dir == 'S': lat_deg = -lat_deg
            if msg.lon_dir == 'W': lon_deg = -lon_deg
            lat = int(lat_deg * 1e7)
            lon = int(lon_deg * 1e7)
            
            # Speed is given in knots, convert to km/h and scale by 100
            speed_knots = float(msg.spd_over_grnd) if msg.spd_over_grnd else 0.0
            speed = int(speed_knots * 1.852 * 100)
        else:
            lat = 0
            lon = 0
            speed = 0

        # Combined 12-byte CAN FD message: lat (4B) + lon (4B) + speed (4B)
        data = (
            lat.to_bytes(4, 'little', signed=True) +
            lon.to_bytes(4, 'little', signed=True) +
            speed.to_bytes(4, 'little', signed=True)
        )
        can_msg = can.Message(
            arbitration_id=0x500,
            data=data,
            is_extended_id=is_extended_id,
            is_fd=can_fd,
            bitrate_switch=bitrate_switch
        )
        bus.send(can_msg, timeout=0.1)

        print(f"Sent: lat={lat/1e7:.6f}, lon={lon/1e7:.6f}, speed={speed/100:.2f} km/h")

    except pynmea2.ParseError:
        continue
    except Exception as e:
        print(f"Error: {e}")
        continue
