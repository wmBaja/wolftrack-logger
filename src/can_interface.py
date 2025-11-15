"""
CAN Bus Interface Module
src/can_interface.py

Manages CAN bus connection and message reading.
Handles threading for non-blocking message reception.
"""

import can
from queue import Queue, Full, Empty
from threading import Thread, Event, Lock
from typing import Optional, Dict, Any
from datetime import datetime
import time

from config import CANConfig
from logging_config import get_logger
from utils.exceptions import CANConnectionException
from utils.can_utils import format_can_data

logger = get_logger(__name__)


class CANInterface:
    """
    CAN bus interface with threaded message reading.
    
    Example:
        >>> config = CANConfig(channel='can0', bitrate=500000)
        >>> can_if = CANInterface(config)
        >>> can_if.connect()
        >>> can_if.start_reading()
        >>> msg = can_if.get_message(timeout=1.0)
        >>> can_if.stop_reading()
        >>> can_if.disconnect()
    """
    
    def __init__(self, config: CANConfig):
        """
        Initialize CAN interface.
        
        Args:
            config: CAN configuration object
        """
        self.config = config
        self.bus: Optional[can.BusABC] = None
        
        # Threading components
        self._message_queue = Queue(maxsize=10000)
        self._reader_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._state_lock = Lock()
        
        # Notifier for broadcasting messages to listeners
        self._notifier: Optional[can.Notifier] = None
        
        # State tracking
        self._is_connected = False
        self._is_reading = False
        
        # Statistics
        self._stats = {
            'messages_read': 0,
            'messages_dropped': 0,
            'read_errors': 0,
            'queue_overflows': 0,
            'start_time': None,
            'last_message_time': None
        }
        self._stats_lock = Lock()
        
        logger.debug(f"CANInterface initialized with config: {config}")
    
    # ========================================================================
    # Connection Management
    # ========================================================================
    
    def connect(self) -> bool:
        """
        Connect to the CAN bus.
        
        Returns:
            True if connection successful
        
        Raises:
            See can.Bus() exceptions
        
        Example:
            >>> can_if.connect()
            True
        """
        with self._state_lock:
            if self._is_connected:
                logger.warning("Already connected to CAN bus")
                return True
            
            try:
                logger.info(f"Connecting to CAN bus: {self.config.channel}")
                logger.debug(f"Interface: {self.config.interface}, "
                           f"Bitrate: {self.config.bitrate}, "
                           f"FD: {self.config.fd}, "
                           f"Data bitrate: {self.config.data_bitrate}")
                
                # Create CAN bus instance
                self.bus = can.Bus(
                    interface=self.config.interface,
                    channel=self.config.channel,
                    bitrate=self.config.bitrate,
                    fd=self.config.fd,
                    data_bitrate=self.config.data_bitrate if self.config.fd else None,
                    receive_own_messages=True
                )
                
                # Create notifier for this bus
                self._notifier = can.Notifier(self.bus, [])
                
                self._is_connected = True
                logger.info(f"Successfully connected to {self.config.channel}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to CAN bus: {e}", exc_info=True)
                raise e
    
    def disconnect(self) -> None:
        """
        Disconnect from the CAN bus.
        
        Stops reading if active and closes the bus connection.
        
        Example:
            >>> can_if.disconnect()
        """

        # Stop reading if active
        if self._is_reading:
            logger.info("Stopping reader before disconnect")
            self.stop_reading()
            
        with self._state_lock:
            if not self._is_connected:
                logger.debug("Not connected, nothing to disconnect")
                return
        
            # Stop notifier
            if self._notifier:
                logger.debug("Stopping notifier")
                self._notifier.stop()
                self._notifier = None
            
            # Close bus connection
            try:
                if self.bus:
                    logger.info(f"Disconnecting from {self.config.channel}")
                    self.bus.shutdown()
                    self.bus = None
                
                self._is_connected = False
                logger.info(f"Disconnected from CAN bus {self.config.channel}")
                
            except Exception as e:
                logger.error(f"Error during CAN bus disconnect: {e}", exc_info=True)
    
    def is_connected(self) -> bool:
        """
        Check if connected to CAN bus.
        
        Returns:
            True if connected
        
        Example:
            >>> can_if.is_connected()
            True
        """
        return self._is_connected
    
    def reconnect(self) -> bool:
        """
        Reconnect to the CAN bus.
        
        Returns:
            True if reconnection successful
        
        Example:
            >>> can_if.reconnect()
            True
        """
        logger.info("Attempting to reconnect...")
        self.disconnect()
        time.sleep(0.5)  # Brief delay before reconnecting
        return self.connect()
    
    # ========================================================================
    # Message Reading
    # ========================================================================
    
    def start_reading(self) -> None:
        """
        Start reading CAN messages in background thread.
        
        Raises:
            CANConnectionException: If not connected
            RuntimeError: If already reading
        
        Example:
            >>> can_if.start_reading()
        """
        with self._state_lock:
            if not self._is_connected:
                raise CANConnectionException("Not connected to CAN bus")
            
            if self._is_reading:
                logger.warning("Already reading messages")
                return
            
            # Reset stop event
            self._stop_event.clear()
            
            # Clear the queue
            self._clear_queue()
            
            # Reset statistics
            with self._stats_lock:
                self._stats['messages_read'] = 0
                self._stats['messages_dropped'] = 0
                self._stats['read_errors'] = 0
                self._stats['queue_overflows'] = 0
                self._stats['start_time'] = datetime.now()
                self._stats['last_message_time'] = None
            
            # Start reader thread
            self._reader_thread = Thread(
                target=self._read_loop,
                name="CANReaderThread",
                daemon=True
            )
            self._reader_thread.start()
            
            self._is_reading = True
            logger.info("Started reading CAN messages")
    
    def stop_reading(self) -> None:
        """
        Stop reading CAN messages.
        
        Waits for reader thread to finish.
        
        Example:
            >>> can_if.stop_reading()
        """
        with self._state_lock:
            if not self._is_reading:
                logger.debug("Not currently reading")
                return

            self._stop_event.set()
            
            # Wait for thread to finish
            if self._reader_thread and self._reader_thread.is_alive():
                self._reader_thread.join(timeout=5.0)
                
                if self._reader_thread.is_alive():
                    logger.warning("Reader thread did not stop cleanly")
                else:
                    logger.debug("Reader thread stopped")
            
            self._is_reading = False
            logger.info("Stopped reading CAN messages")
    
    def is_reading(self) -> bool:
        """
        Check if currently reading messages.
        
        Returns:
            True if reading
        
        Example:
            >>> can_if.is_reading()
            True
        """
        return self._is_reading
    
    def _read_loop(self) -> None:
        """
        Main loop for reading CAN messages (runs in thread).
        
        This method continuously reads messages from the CAN bus
        and places them in the queue until stopped.
        """
        logger.info("CAN reader thread started")
        
        # Create local reference (also slightly faster - avoids repeated attribute lookup)
        bus = self.bus
        if bus is None:
            logger.error("Read loop started without bus connection")
            return
        
        while not self._stop_event.is_set():
            try:
                msg = bus.recv(timeout=0.1)
                
                if msg is not None:
                    # Update statistics
                    with self._stats_lock:
                        self._stats['messages_read'] += 1
                        self._stats['last_message_time'] = datetime.now()
                    
                    # Try to put message in queue
                    try:
                        self._message_queue.put(msg, block=False)
                        
                        logger.debug(
                            f"CAN RX: {(msg.arbitration_id)} "
                            f"[{msg.dlc}] {format_can_data(msg.data)}"
                        )
                    
                    except Full:
                        # Queue is full, drop message
                        with self._stats_lock:
                            self._stats['messages_dropped'] += 1
                            self._stats['queue_overflows'] += 1
                        
                        if self._stats['messages_dropped'] % 100 == 1:
                            logger.warning(
                                f"Message queue full, dropped {self._stats['messages_dropped']} messages"
                            )
            
            except Exception as e:
                # Log error but continue reading
                with self._stats_lock:
                    self._stats['read_errors'] += 1
                
                if self._stats['read_errors'] % 10 == 1:
                    logger.error(f"Error reading CAN message: {e}")
                
                # Brief delay on error to avoid tight loop
                time.sleep(0.01)
        
        logger.debug("CAN reader thread stopped")
    
    def get_message(self, timeout: float = 0.1) -> Optional[can.Message]:
        """
        Get next message from queue.
        
        Args:
            timeout: Maximum time to wait for message (seconds)
        
        Returns:
            CAN message or None if timeout
        
        Example:
            >>> msg = can_if.get_message(timeout=1.0)
            >>> if msg:
            ...     print(f"Got message: {msg.arbitration_id:X}")
        """
        try:
            return self._message_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def _clear_queue(self) -> int:
        """
        Clear all messages from queue.
        
        Returns:
            Number of messages cleared
        """
        count = 0
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
                count += 1
            except Empty:
                break
        
        if count > 0:
            logger.debug(f"Cleared {count} messages from queue")
        
        return count
    
    # ========================================================================
    # Message Sending (optional, for testing)
    # ========================================================================
    
    def send_message(self, msg: can.Message) -> bool:
        """
        Send a CAN message object.
        
        Args:
            msg: CAN message object
        
        Returns:
            True if sent successfully
        
        Example:
            >>> msg = can.Message(arbitration_id=0x123, data=bytes([0x01, 0x02]))
            >>> can_if.send_message(msg)
            True
        """
        if not self._is_connected or self.bus is None:
            logger.error("Cannot send: not connected")
            return False
        
        try:
            # Send message
            self.bus.send(msg)
            
            logger.debug(
                f"CAN TX: {(msg.arbitration_id, msg.is_extended_id)} "
                f"[{msg.dlc}] {format_can_data(msg.data)}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    def send_message_raw(self, can_id: int, data: bytes, is_extended: bool = False) -> bool:
        return self.send_message(can.Message(arbitration_id=can_id, data=data, is_extended_id=is_extended))
    
    # ========================================================================
    # Statistics and Monitoring
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics.
        
        Returns:
            Dictionary with statistics
        
        Example:
            >>> stats = can_if.get_stats()
            >>> print(f"Messages read: {stats['messages_read']}")
        """
        with self._stats_lock:
            stats = self._stats.copy()
        
        # Add computed fields
        stats['queue_size'] = self._message_queue.qsize()
        stats['is_connected'] = self._is_connected
        stats['is_reading'] = self._is_reading
        
        # Calculate uptime
        if stats['start_time']:
            uptime = (datetime.now() - stats['start_time']).total_seconds()
            stats['uptime_seconds'] = uptime
            
            # Calculate message rate
            if uptime > 0:
                stats['messages_per_second'] = stats['messages_read'] / uptime
            else:
                stats['messages_per_second'] = 0.0
        else:
            stats['uptime_seconds'] = 0.0
            stats['messages_per_second'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """
        Reset statistics counters.
        
        Example:
            >>> can_if.reset_stats()
        """
        with self._stats_lock:
            self._stats['messages_read'] = 0
            self._stats['messages_dropped'] = 0
            self._stats['read_errors'] = 0
            self._stats['queue_overflows'] = 0
            self._stats['start_time'] = datetime.now() if self._is_reading else None
            self._stats['last_message_time'] = None
        
        logger.debug(f"CAN Bus {self.config.channel} Statistics reset")
    
    # ========================================================================
    # Listener Management
    # ========================================================================
    
    def add_listener(self, listener) -> None:
        """
        Add a listener to receive CAN messages.
        
        Args:
            listener: Object with on_message_received(msg) method or callable
        
        Example:
            >>> logger = can.Logger('output.mf4')
            >>> can_if.add_listener(logger)
        """
        if not self._is_connected or self._notifier is None:
            raise CANConnectionException("Not connected to CAN bus")
        
        self._notifier.add_listener(listener)
        logger.info(f"Added listener: {type(listener).__name__}")
    
    def remove_listener(self, listener) -> None:
        """
        Remove a listener from receiving CAN messages.
        
        Args:
            listener: Previously added listener object
        
        Example:
            >>> can_if.remove_listener(logger)
        """
        if not self._is_connected or self._notifier is None:
            logger.warning("Cannot remove listener: not connected")
            return
        
        try:
            self._notifier.remove_listener(listener)
            logger.info(f"Removed listener: {type(listener).__name__}")
        except ValueError:
            logger.warning(f"Listener not found: {type(listener).__name__}")
    
    def get_listeners(self) -> list:
        """
        Get list of active listeners.
        
        Returns:
            List of listener objects
        
        Example:
            >>> listeners = can_if.get_listeners()
            >>> print(f"Active listeners: {len(listeners)}")
        """
        if self._notifier is None:
            return []
        return self._notifier.listeners.copy()
    
    # ========================================================================
    # Context Manager Support
    # ========================================================================
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False
    
    # ========================================================================
    # Cleanup
    # ========================================================================
    
    def __del__(self):
        """Destructor - ensure cleanup"""
        try:
            if self._is_connected or self._is_reading:
                logger.debug("Cleaning up CANInterface")
                self.disconnect()
        except:
            pass


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == '__main__':
    from config import CANConfig
    from logging_config import setup_logging
    
    # Setup logging
    setup_logging(
        log_dir='./app_logs',
        log_level='DEBUG',
        console_output=True,
        log_to_file=True,
        max_file_size_mb=10000,
        backup_count=5,
        format_style='detailed'
    )
    
    
    print("=== CAN Interface Test ===\n")
    
    # Create configuration
    config = CANConfig(
        interface='virtual',  
        channel='vcan0',  
        bitrate=500000,
        fd=True,
        data_bitrate=2000000
    )
    
    # Create interface
    can_if = CANInterface(config)
    
    try:
        # Connect
        print("Connecting to CAN bus...")
        can_if.connect()
        print(f"✓ Connected: {can_if.is_connected()}\n")
        
        # Start reading
        print("Starting message reader...")
        can_if.start_reading()
        print(f"✓ Reading: {can_if.is_reading()}\n")
        
        # Read messages for 5 seconds
        print("Reading messages for 5 seconds...")
        start_time = time.time()
        message_count = 0
        
        while time.time() - start_time < 5.0:
            msg = can_if.get_message(timeout=0.1)
            if msg:
                message_count += 1
                print(f"  RX: {(msg.arbitration_id)} "
                      f"[{msg.dlc}] {format_can_data(msg.data)}")
        
        print(f"\n✓ Received {message_count} messages\n")
        
        # Get statistics
        stats = can_if.get_stats()
        print("=== Statistics ===")
        print(f"Messages read: {stats['messages_read']}")
        print(f"Messages dropped: {stats['messages_dropped']}")
        print(f"Read errors: {stats['read_errors']}")
        print(f"Queue size: {stats['queue_size']}")
        print(f"Uptime: {stats['uptime_seconds']:.1f}s")
        print(f"Messages/sec: {stats['messages_per_second']:.1f}")
        
    except CANConnectionException as e:
        print(f"✗ Connection error: {e}")
        print("\nTroubleshooting:")
        print("1. Check CAN interface exists: ip link show can0")
        print("2. Bring up interface: sudo ip link set can0 up type can bitrate 500000")
        print("3. For testing, use virtual CAN: sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0")
    
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        can_if.disconnect()
        print("✓ Done")