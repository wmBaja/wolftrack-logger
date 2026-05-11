"""
ZMQ Stream Listener
Publishes batched raw CAN messages to a ZeroMQ PUB socket.
External clients (like the visualizer) connect to this to receive live data.
"""
import can
import zmq
import threading
import time
from collections import deque
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
        
        self.lock = threading.Lock()
        self.frame_buffer = []
        # Capped to ~500ms of data at 25ms per batch (40 batches/sec -> 20 batches = 500ms)
        self.unpublished_queue = deque(maxlen=20)
        self.dropped_batches = 0
        
        self.running = True
        self.publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publish_thread.start()
        
    def on_message_received(self, msg: can.Message):
        payload = {
            "timestamp": msg.timestamp,
            "arbitration_id": msg.arbitration_id,
            "data": list(msg.data),  # json serializable
            "dlc": msg.dlc,
            "is_extended_id": msg.is_extended_id,
            "is_error_frame": msg.is_error_frame,
            "channel": msg.channel
        }
        
        with self.lock:
            self.frame_buffer.append(payload)
            if len(self.frame_buffer) >= 256:
                self._enqueue_current_buffer()

    def _enqueue_current_buffer(self):
        if not self.frame_buffer:
            return
        
        if len(self.unpublished_queue) == self.unpublished_queue.maxlen:
            self.dropped_batches += 1
            
        self.unpublished_queue.append(list(self.frame_buffer))
        self.frame_buffer.clear()

    def _publish_loop(self):
        while self.running:
            with self.lock:
                self._enqueue_current_buffer()
                
            while True:
                batch = None
                with self.lock:
                    if self.unpublished_queue:
                        batch = self.unpublished_queue.popleft()
                        dropped = self.dropped_batches
                        self.dropped_batches = 0
                    else:
                        break
                        
                if batch:
                    try:
                        payload = {
                            "type": "can_batch",
                            "frames": batch,
                            "dropped_batches": dropped
                        }
                        # ZMQ sends this as a UTF-8 encoded JSON string
                        self.socket.send_json(payload)
                    except Exception as e:
                        logger.debug(f"Failed to publish CAN batch over ZMQ: {e}")
            
            # 25 ms interval
            time.sleep(0.025)

    def stop(self):
        """Clean up the ZMQ socket context safely."""
        self.running = False
        if self.publish_thread.is_alive():
            self.publish_thread.join(timeout=1.0)
            
        try:
            self.socket.close()
            self.context.term()
            logger.info("ZmqStreamListener closed.")
        except Exception as e:
            logger.error(f"Error closing ZmqStreamListener: {e}")
