import cantools
from pathlib import Path
from typing import List, Optional, Dict, Any
import can

from logging_config import get_logger
from utils.exceptions import DBCLoadException

logger = get_logger(__name__)

class DBCManager:
    """Loads, encodes, and decodes CAN messages based on given DBC file."""

    def __init__(self, dbc_dir: str = './dbc'):
        self.dbc_dir = Path(dbc_dir)
        self.db = None
        self.dbc_name = None

        # Ensure DBC directory exists
        self.dbc_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"DBCManager initialized with directory: {self.dbc_dir}")
    
    def load_dbc(self, dbc_path: str) -> bool:
        try:
            # Resolve path
            path = Path(dbc_path)
            if not path.is_absolute():
                path = self.dbc_dir / path
            
            # Validate path
            if not path.exists():
                raise DBCLoadException(f"DBC file not found: {path}")
            
            if not path.suffix == '.dbc':
                raise DBCLoadException(f"File must have .dbc extension: {path}")
            
            logger.info(f"Loading DBC file: {path}")
            
            # Load DBC file
            self.db = cantools.database.load_file(str(path))
            self.dbc_name = path.stem
            
            # Log info
            signal_count = sum(len(msg.signals) for msg in self.db.messages)
            logger.info(
                f"Loaded DBC '{self.dbc_name}': "
                f"{len(self.db.messages)} messages, "
                f"{signal_count} signals"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load DBC: {e}", exc_info=True)
            raise DBCLoadException(f"Failed to load DBC: {e}")
    
    def is_loaded(self) -> bool:
        return self.db is not None
    
    def unload_dbc(self) -> None:
        if self.db:
            logger.info(f"Unloading DBC '{self.dbc_name}'")
            self.db = None
            self.dbc_name = None

    def decode_message(self, msg: can.Message) -> Dict[str, Any] | None:
        if not self.db:
            logger.debug("No DBC loaded")
            return None
        
        try:
            # Find message definition by CAN ID
            message_def = self.db.get_message_by_frame_id(msg.arbitration_id)
            
            # Decode message
            decoded = message_def.decode(msg.data)

            logger.debug(
                f"Decoded 0x{msg.arbitration_id:X} ({message_def.name}): {decoded}"
            )
            
            return decoded
            
        except KeyError:
            return None
            
        except Exception as e:
            return None

    def encode_message(self, can_id: int, data: int) -> can.Message | None:
        if not self.db:
            logger.debug("No DBC loaded")
            return None

        try:
            # Find message definition by CAN ID
            message_def = self.db.get_message_by_frame_id(can_id)

            # Encode message
            encoded_data = message_def.encode(data)

            logger.debug(
                f"Encoded 0x{msg.arbitration_id:X} ({message_def.name}): {encoded_data}"
            )

            # Create new CAN message with encoded data
            encoded_msg = can.Message(
                arbitration_id=msg.arbitration_id,
                data=encoded_data,
                is_extended_id=msg.is_extended_id
            )

            return encoded_msg

        except KeyError:
            return msg

        except Exception as e:
            return msg
    
    def id_in_dbc(self, can_id: int) -> bool:
        if not self.db:
            return False
        
        try:
            self.db.get_message_by_frame_id(can_id)
            return True
        except KeyError:
            return False
    
    def get_message_info(self, can_id: int) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        
        try:
            message_def = self.db.get_message_by_frame_id(can_id)

            return {
                'name': message_def.name,
                'can_id': message_def.frame_id,
                'dlc': message_def.length,
                'cycle_time': message_def.cycle_time,
                'senders': message_def.senders,
                'comment': message_def.comment,
                'signals': [signal.name for signal in message_def.signals],
                'signal_count': len(message_def.signals)
            }
            
        except KeyError:
            return None
    
    def get_signal_info(self, can_id: int, signal_name: str) -> Optional[Dict[str, Any]]:
        if not self.db:
            return None
        
        try:
            message_def = self.db.get_message_by_frame_id(can_id)
            
            # Find signal
            for sig in message_def.signals:
                if sig.name == signal_name:
                    return {
                        'name': sig.name,
                        'unit': sig.unit,
                        'minimum': sig.minimum,
                        'maximum': sig.maximum,
                        'offset': sig.offset,
                        'scale': sig.scale,
                        'start_bit': sig.start,
                        'length': sig.length,
                        'byte_order': sig.byte_order,
                        'comment': sig.comment
                    }
            
            return None
            
        except KeyError:
            return None
    
    def get_database_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about loaded database.
        
        Returns:
            Dictionary with database information or None
        
        Example:
            >>> info = dbc_mgr.get_database_info()
            >>> print(f"Messages: {info['message_count']}")
            >>> print(f"Signals: {info['signal_count']}")
        """
        if not self.db:
            return None
        
        # Count signals
        total_signals = sum(len(msg.signals) for msg in self.db.messages)
        
        return {
            'name': self.dbc_name,
            'version': self.db.version,
            'message_count': len(self.db.messages),
            'signal_count': total_signals,
            'node_count': len(self.db.nodes) if hasattr(self.db, 'nodes') else 0,
            'messages': [
                {
                    'name': msg.name,
                    'can_id': msg.frame_id,
                    'signal_count': len(msg.signals)
                }
                for msg in self.db.messages
            ]
        }
    
    def list_all_signals(self) -> Dict[int, List[str]]:
        if not self.db:
            return {}
        
        result = {}
        for msg in self.db.messages:
            result[msg.frame_id] = [sig.name for sig in msg.signals]
        
        return result

if __name__ == '__main__':
    from logging_config import setup_logging

    setup_logging(
        log_dir='./app_logs',
        log_level='DEBUG',
        console_output=True,
        log_to_file=True,
        max_file_size_mb=10000,
        backup_count=5,
        format_style='detailed'
    )

    print("=== Simple DBC Manager Test ===\n")
    
    # Create manager
    dbc_mgr = DBCManager('./dbc')
    
    # Check for DBC files
    dbc_files = list(Path('./dbc').glob('*.dbc'))
    
    if not dbc_files:
        print("No DBC files found in ./dbc/")
        print("\nPlace a .dbc file there and run again.")
    else:
        print(f"Found DBC file: {dbc_files[0].name}\n")
        
        # Load first DBC
        try:
            dbc_mgr.load_dbc(dbc_files[0].name)
            print(f"✓ Loaded DBC: {dbc_mgr.dbc_name}\n")
            
            # Show info
            info = dbc_mgr.get_database_info()
            if info:
                print("=== Database Info ===")
                print(f"Messages: {info['message_count']}")
                print(f"Signals: {info['signal_count']}")
                print(f"Nodes: {info['node_count']}")
                print()
                
                # Show first few messages
                print("=== First 5 Messages ===")
                for msg in info['messages'][:5]:
                    print(f"  0x{msg['can_id']:03X} - {msg['name']} "
                          f"({msg['signal_count']} signals)")
            
        except DBCLoadException as e:
            print(f"✗ Failed to load DBC: {e}")
    
    print("\nDone")