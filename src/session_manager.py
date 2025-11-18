import re
import can
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
import time
from threading import Lock

from can_interface import CANInterface
from dbc_manager import DBCManager
from config import CANLogConfig
from logging_config import get_logger
from utils.exceptions import (
    SessionAlreadyActiveException,
    SessionNotActiveException,
    FileNameValidationException
)

logger = get_logger(__name__)


def _validate_filename_template(template: str, allowed_placeholders: List[str] = None) -> bool:
    if allowed_placeholders is None:
        allowed_placeholders = [
            'C', 'T', 'Y', 'm', 'd', 'H', 'M', 'S'
        ]

    placeholders = re.findall(r'\%(\w)', template)

    for placeholder in placeholders:
        if placeholder not in allowed_placeholders:
            raise FileNameValidationException(
                f"Invalid placeholder '{{{placeholder}}}'. "
                f"Allowed: {', '.join(['%' + p for p in allowed_placeholders])}"
            )

    return True


class SessionManager:
    def __init__(self, can_interface: CANInterface, dbc_manager: DBCManager, can_log_config: CANLogConfig):
        self.can_interface = can_interface
        self.dbc_manager = dbc_manager
        self.can_log_config = can_log_config

        self._state_lock = Lock()
        self._is_active = False
        self._session_name: Optional[str] = None
        self._output_file: Optional[Path] = None

        self._mf4_logger: Optional[can.Logger] = None
        
        # Session statistics
        self._start_time: Optional[datetime] = None

        logger.debug("SessionManager initialized")

    def start(self, filename_template: Optional[str] = None) -> Tuple[bool, str]:
        with self._state_lock:
            if self._is_active:
                raise SessionAlreadyActiveException("Session already active")

            try:
                self._session_name = self._generate_session_name(filename_template)
                self._output_file = Path(self.can_log_config.output_dir) / f"{self._session_name}.mf4"

                self._output_file.parent.mkdir(parents=True, exist_ok=True)

                logger.info(f"Starting session: {self._session_name}")
                logger.info(f"Output file: {self._output_file}")

                # Reset statistics
                self._start_time = datetime.now()

                # Get DBC path if loaded
                dbc_path = None
                if self.dbc_manager.is_loaded():
                    dbc_path = Path(self.dbc_manager.dbc_dir, f"{self.dbc_manager.dbc_name}.dbc")

                if not self.can_interface.is_connected():
                    self.can_interface.connect()

                self.can_interface.send_message(
                    self.can_interface.config.daq_messages['wake_up']
                )
                logger.debug(f"Sending wake-up message: {self.can_interface.config.daq_messages['wake_up']}")
                
                # Small delay to ensure wake-up is processed
                time.sleep(0.1)

                # Create MF4 logger
                self._mf4_logger = can.Logger(
                    str(self._output_file),
                    database=dbc_path,
                    compression=self.can_log_config.compression
                )
                logger.info("MF4 CAN logger created")

                # Add logger as listener to CAN interface
                self.can_interface.add_listener(self._mf4_logger)
                logger.debug("MF4 logger added as listener")

                self._is_active = True

                logger.info("Session started successfully")
                return True, f"Session started: {self._session_name}"

            except Exception as e:
                logger.error(f"Failed to start session: {e}", exc_info=True)
                self._cleanup_failed_start()
                return False, f"Failed to start session: {e}"

    def stop(self) -> Tuple[bool, str]:
        with self._state_lock:
            if not self._is_active:
                raise SessionNotActiveException("No active session")

            try:
                logger.info(f"Stopping session: {self._session_name}")

                # Remove logger from listeners and stop it
                if self._mf4_logger:
                    self.can_interface.remove_listener(self._mf4_logger)
                    self._mf4_logger.stop()
                    self._mf4_logger = None

                # Calculate duration
                duration = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0

                # Get file size
                file_size = 0
                if self._output_file and self._output_file.exists():
                    file_size = self._output_file.stat().st_size

                self._is_active = False

                message = (
                    f"Session stopped: {self._session_name}. "
                    f"Duration: {duration:.1f}s, "
                    f"File size: {file_size:,} bytes"
                )

                logger.info(message)
                logger.info(f"Output file: {self._output_file}, "
                            f"File size: {file_size} bytes")

                self.can_interface.send_message(
                    self.can_interface.config.daq_messages['standby']
                )

                return True, message

            except Exception as e:
                logger.error(f"Error stopping session: {e}", exc_info=True)
                return False, f"Error stopping session: {e}"

    def is_active(self) -> bool:
        return self._is_active

    def get_status(self) -> Dict[str, Any]:
        """
        Get current session status and statistics.
        
        Returns:
            Dictionary containing session status and stats
        """
        uptime = 0.0
        if self._is_active and self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        file_size = 0
        if self._output_file and self._output_file.exists():
            file_size = self._output_file.stat().st_size

        status = {
            'is_active': self._is_active,
            'session_name': self._session_name,
            'output_file': str(self._output_file) if self._output_file else None,
            'start_time': self._start_time.isoformat() if self._start_time else None,
            'uptime_seconds': uptime,
            'file_size_bytes': file_size,
            'can_connected': self.can_interface.is_connected(),
            'can_channel': self.can_interface.config.channel,
            'can_bitrate': self.can_interface.config.bitrate,
            'dbc_loaded': self.dbc_manager.is_loaded(),
            'dbc_name': self.dbc_manager.dbc_name if self.dbc_manager.is_loaded() else None,
            'active_listeners': len(self.can_interface.get_listeners())
        }

        return status

    def _generate_session_name(self, template: Optional[str]) -> str:
        if not template:
            template = self.can_log_config.default_filename_template

        try:
            _validate_filename_template(template)
        except FileNameValidationException as e:
            logger.error(f"Filename template validation error: {e}\nUsing default template instead.")
            template = self.can_log_config.default_filename_template

        now = datetime.now()

        replacements = {
            '%C': f'{self._get_next_counter():03d}',
            '%T': now.strftime('%Y%m%d_%H%M%S'),
            '%Y': now.strftime('%Y'),
            '%m': now.strftime('%m'),
            '%d': now.strftime('%d'),
            '%H': now.strftime('%H'),
            '%M': now.strftime('%M'),
            '%S': now.strftime('%S'),
        }

        session_name = template
        for placeholder, value in replacements.items():
            session_name = session_name.replace(placeholder, value)

        # Remove .mf4 extension if present (we'll add it when creating the file)
        if session_name.endswith('.mf4'):
            session_name = session_name[:-4]

        return session_name

    def _get_next_counter(self) -> int:
        output_dir = Path(self.can_log_config.output_dir)
        if not output_dir.exists():
            return 0

        existing = list(output_dir.glob('*.mf4'))
        return len(existing)

    def _cleanup_failed_start(self) -> None:
        """Cleanup after failed session start"""
        try:
            if self._mf4_logger:
                self.can_interface.remove_listener(self._mf4_logger)
                self._mf4_logger.stop()
                self._mf4_logger = None
            if self._output_file and self._output_file.exists():
                self._output_file.unlink()
            self._is_active = False
            self._start_time = None
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

if __name__ == '__main__':
    from logging_config import setup_logging
    from config import CANConfig, CANLogConfig

    # Setup logging
    setup_logging(
        log_dir='./app_logs',
        log_level='DEBUG',
        console_output=True,
        log_to_file=True,
        max_file_size_mb=10,
        backup_count=5,
        format_style='detailed'
    )

    print("=== Session Manager Test ===\n")

    # Create components
    can_config = CANConfig(interface='virtual', channel='vcan0')
    log_config = CANLogConfig()

    can_interface = CANInterface(can_config)
    dbc_manager = DBCManager(log_config.dbc_dir)
    session_manager = SessionManager(can_interface, dbc_manager, log_config)

    # Load DBC if available
    try:
        dbc_manager.load_dbc('motohawk.dbc')
    except:
        print("No DBC loaded (optional)")

    try:
        # Start session
        print("Starting session...")
        success, msg = session_manager.start('test_session_%T')
        print(f"✓ {msg}\n")

        # Monitor for 10 seconds
        print("Logging for 10 seconds...")
        for i in range(10):
            time.sleep(1)
            status = session_manager.get_status()
            print(f"  [{i+1}s] File: {status['file_size_bytes']:,} bytes, "
                  f"Listeners: {status['active_listeners']}")
            
            # Send some test messages
            if i % 2 == 0:
                can_interface.send_message_raw(0x123, bytes([i, 0x11, 0x22, 0x33]))

        # Stop session
        print("\nStopping session...")
        success, msg = session_manager.stop()
        print(f"✓ {msg}")

        # Final status
        status = session_manager.get_status()
        print(f"\nFinal file: {status['output_file']}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        can_interface.disconnect()

    print("\n✓ Done")