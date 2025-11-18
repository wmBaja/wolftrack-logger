"""
CAN Bus Interface Module
src/can_interface.py

Manages CAN bus connection and message listeners.
Uses python-can's Notifier system for message distribution.
"""

import can
from typing import Optional
import time

from config import CANConfig
from logging_config import get_logger
from utils.exceptions import CANConnectionException
from utils.can_utils import format_can_data

logger = get_logger(__name__)


class CANInterface:
    """
    CAN bus interface using notifier-based message distribution.
    
    Example:
        >>> config = CANConfig(channel='can0', bitrate=500000)
        >>> can_if = CANInterface(config)
        >>> can_if.connect()
        >>> logger = can.Logger('output.mf4')
        >>> can_if.add_listener(logger)
        >>> # Messages are now automatically logged
        >>> can_if.remove_listener(logger)
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
        
        # Notifier for broadcasting messages to listeners
        self._notifier: Optional[can.Notifier] = None
        
        # State tracking
        self._is_connected = False
        
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
        
        Stops all listeners and closes the bus connection.
        
        Example:
            >>> can_if.disconnect()
        """
        if not self._is_connected:
            logger.debug("Not connected, nothing to disconnect")
            return
    
        # Stop notifier
        if self._notifier:
            logger.debug("Stopping notifier and all listeners")
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
    # Message Sending
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
                f"CAN TX: ID=0x{msg.arbitration_id:X} "
                f"[{msg.dlc}] {format_can_data(msg.data)}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            return False

    def send_message_raw(self, can_id: int, data: bytes, is_extended: bool = False) -> bool:
        """
        Send a CAN message with raw parameters.
        
        Args:
            can_id: CAN arbitration ID
            data: Message data bytes
            is_extended: True for extended (29-bit) ID
        
        Returns:
            True if sent successfully
        
        Example:
            >>> can_if.send_message_raw(0x123, bytes([0x01, 0x02]))
            True
        """
        return self.send_message(
            can.Message(
                arbitration_id=can_id, 
                data=data, 
                is_extended_id=is_extended
            )
        )
    
    # ========================================================================
    # Listener Management
    # ========================================================================
    
    def add_listener(self, listener) -> None:
        """
        Add a listener to receive CAN messages.
        
        Args:
            listener: Listener object or callable
        
        Raises:
            CANConnectionException: If not connected to bus
        
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
        return list(self._notifier.listeners)
    
    def clear_listeners(self) -> None:
        """
        Remove all listeners.
        
        Example:
            >>> can_if.clear_listeners()
        """
        if self._notifier is None:
            return
        
        listeners = list(self._notifier.listeners)
        for listener in listeners:
            self.remove_listener(listener)
        
        logger.info("Cleared all listeners")
    
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
            if self._is_connected:
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
        
        # Create a simple message printer listener
        class MessagePrinter(can.Listener):
            def __init__(self):
                self.count = 0
            
            def on_message_received(self, msg):
                self.count += 1
                print(f"  [{self.count}] RX: ID=0x{msg.arbitration_id:03X} "
                      f"[{msg.dlc}] {format_can_data(msg.data)}")
        
        # Add listener
        printer = MessagePrinter()
        can_if.add_listener(printer)
        print("✓ Added message printer listener\n")
        
        # Send some test messages
        print("Sending test messages...")
        for i in range(5):
            can_if.send_message_raw(0x123, bytes([i, 0x11, 0x22, 0x33]))
            time.sleep(0.5)
        
        print(f"\n✓ Received {printer.count} messages\n")
        
        # Show active listeners
        print(f"Active listeners: {len(can_if.get_listeners())}")
        
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