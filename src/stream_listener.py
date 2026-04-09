"""
ZMQ Stream Listener
Publishes raw CAN messages to a ZeroMQ PUB socket.
External clients (like the visualizer) connect to this to receive live data.
"""
import can
import zmq
from logging_config import get_logger

logger = get_logger(__name__)

class ZmqStreamListener(can.Listener):
    def __init__(self, port: int = 5555):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        # Bind to 0.0.0.0 so clients on the network can connect
        addr = f"tcp://0.0.0.0:{port}"
        self.socket.bind(addr)
        logger.info(f"ZmqStreamListener bound to {addr}")
        
    def on_message_received(self, msg: can.Message):
        """Called automatically by can.Notifier for every message received."""
        try:
            # Publish RAW CAN message frame
            payload = {
                "timestamp": msg.timestamp,
                "arbitration_id": msg.arbitration_id,
                "data": list(msg.data),  # json serializable
                "dlc": msg.dlc,
                "is_extended_id": msg.is_extended_id,
                "is_error_frame": msg.is_error_frame,
                "channel": msg.channel
            }
            # ZMQ sends this as a UTF-8 encoded JSON string
            self.socket.send_json(payload)
        except Exception as e:
            logger.debug(f"Failed to publish CAN message over ZMQ: {e}")
            
    def stop(self):
        """Clean up the ZMQ socket context safely."""
        try:
            self.socket.close()
            self.context.term()
            logger.info("ZmqStreamListener closed.")
        except Exception as e:
            logger.error(f"Error closing ZmqStreamListener: {e}")
