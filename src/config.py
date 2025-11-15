"""
Configuration module for CAN Logger Backend
src/config.py

Defines all configuration dataclasses and loading methods.
"""

from typing import Dict
from dataclasses import dataclass, field
from pathlib import Path
from can import Message
import os

@dataclass
class CANConfig:
    """CAN bus hardware configuration"""
    
    interface: str = 'socketcan'
    channel: str = 'can0'
    bitrate: int = 500000
    fd: bool = True  # CAN-FD support
    data_bitrate: int = 2000000  # CAN-FD data phase bitrate
    daq_messages: Dict[str, Message] = field(default_factory=dict)
    
    @classmethod
    def from_env(cls) -> 'CANConfig':
        """Load configuration from environment variables"""
        return cls(
            interface=os.getenv('CAN_INTERFACE', 'socketcan'),
            channel=os.getenv('CAN_CHANNEL', 'can0'),
            bitrate=int(os.getenv('CAN_BITRATE', '500000')),
            fd=os.getenv('CAN_FD', 'true').lower() == 'true',
            data_bitrate=int(os.getenv('CAN_DATA_BITRATE', '2000000'))
        )
    
    def __post_init__(self):
        if not self.daq_messages:
            self.daq_messages = {
                'standby': Message(arbitration_id=0x00000000, data=bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), is_extended_id=True),
                'wake_up': Message(arbitration_id=0x00000000, data=bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]), is_extended_id=True),
            }
    
    def __repr__(self) -> str:
        return (f"CANConfig(interface={self.interface}, channel={self.channel}, "
                f"bitrate={self.bitrate}, fd={self.fd}, data_bitrate={self.data_bitrate})")


@dataclass
class CANLogConfig:
    """MDF4 logging configuration"""
    
    output_dir: str = './logs'
    dbc_dir: str = './dbc'
    max_file_size_mb: int = 100
    compression: int = 2  # MDF4 compression level (0=none, 1=deflate, 2=transposition+deflate)
    buffer_size: int = 10000  # Message queue size
    default_filename_template: str = 'log_%T.mf4'  # Default log file naming template
    
    @classmethod
    def from_env(cls) -> 'CANLogConfig':
        """Load configuration from environment variables"""
        return cls(
            output_dir=os.getenv('LOG_OUTPUT_DIR', './logs'),
            dbc_dir=os.getenv('DBC_DIR', './dbc_files'),
            max_file_size_mb=int(os.getenv('LOG_MAX_FILE_SIZE_MB', '100')),
            compression=int(os.getenv('LOG_COMPRESSION', '2')),
            buffer_size=int(os.getenv('LOG_BUFFER_SIZE', '10000')),
            default_filename_template=os.getenv('LOG_FILE_TEMPLATE', 'log_%T.mf4')
        )
    
    def __post_init__(self):
        """Create directories if they don't exist"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.dbc_dir).mkdir(parents=True, exist_ok=True)
    
    def __repr__(self) -> str:
        return (f"LogConfig(output_dir={self.output_dir}, dbc_dir={self.dbc_dir}, "
                f"compression={self.compression})")

@dataclass
class AppLogConfig:
    """Application logging configuration"""
    
    log_dir: str = './app.log'
    log_level: str = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_to_console: bool = True
    log_to_file: bool = True
    max_log_file_size_mb: int = 10  # Max size for log file before rotation
    log_backup_count: int = 5  # Number of backup log files to keep
    log_format : str = 'detailed'  # 'simple' or 'detailed'
    
    @classmethod
    def from_env(cls) -> 'AppLogConfig':
        """Load configuration from environment variables"""
        return cls(
            log_dir=os.getenv('APP_LOG_DIR', './app.log'),
            log_level=os.getenv('APP_LOG_LEVEL', 'INFO').upper(),
            log_to_console=os.getenv('APP_LOG_TO_CONSOLE', 'true').lower() == 'true',
            log_to_file=os.getenv('APP_LOG_TO_FILE', 'true').lower() == 'true',
            max_log_file_size_mb=int(os.getenv('APP_LOG_MAX_FILE_SIZE_MB', '10')),
            log_backup_count=int(os.getenv('APP_LOG_BACKUP_COUNT', '5')),
            log_format=os.getenv('APP_LOG_FORMAT', 'detailed')
        )
    
    def __repr__(self) -> str:
        return (f"AppLogConfig(log_dir={self.log_dir}, log_level={self.log_level}, "
                f"log_to_console={self.log_to_console}, log_to_file={self.log_to_file}, "
                f"max_log_file_size_mb={self.max_log_file_size_mb}, log_backup_count={self.log_backup_count}, "
                f"log_format={self.log_format})")

@dataclass
class FlaskConfig:
    """Flask application configuration"""
    
    host: str = '0.0.0.0'
    port: int = 5000
    debug: bool = False # Enable/disable debug mode for Flask app 
    enable_cors: bool = True  # Enable/disable CORS for API

    @classmethod
    def from_env(cls) -> 'FlaskConfig':
        """Load configuration from environment variables"""
        return cls(
            host=os.getenv('FLASK_HOST', '0.0.0.0'),
            port=int(os.getenv('FLASK_PORT', '5000')),
            debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
            enable_cors=os.getenv('ENABLE_CORS', 'true').lower() == 'true'
        )
    
    def __repr__(self) -> str:
        return (f"FlaskConfig(host={self.host}, port={self.port}, debug={self.debug}, "
                f"enable_cors={self.enable_cors})")

@dataclass
class AppConfig:
    """Main application configuration"""
    
    can: CANConfig = field(default_factory=CANConfig)
    canlog: CANLogConfig = field(default_factory=CANLogConfig)
    appLog: AppLogConfig = field(default_factory=AppLogConfig)
    flask: FlaskConfig = field(default_factory=FlaskConfig)
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Load entire configuration from environment variables"""
        return cls(
            can=CANConfig.from_env(),
            canlog=CANLogConfig.from_env(),
            appLog=AppLogConfig.from_env(),
            flask=FlaskConfig.from_env()
        )
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'AppConfig':
        """Load configuration from dictionary (for config files)"""
        can_config = CANConfig(**config_dict.get('can', {}))
        log_config = CANLogConfig(**config_dict.get('log', {}))
        app_log_config = AppLogConfig(**config_dict.get('appLog', {}))
        flask_config = FlaskConfig(**config_dict.get('flask', {}))
        
        return cls(
            can=can_config,
            canlog=log_config,
            appLog=app_log_config,
            flask=flask_config
        )
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            'can': {
                'interface': self.can.interface,
                'channel': self.can.channel,
                'bitrate': self.can.bitrate,
                'fd': self.can.fd,
                'data_bitrate': self.can.data_bitrate
            },
            'log': {
                'output_dir': self.canlog.output_dir,
                'dbc_dir': self.canlog.dbc_dir,
                'max_file_size_mb': self.canlog.max_file_size_mb,
                'compression': self.canlog.compression,
                'buffer_size': self.canlog.buffer_size,
                'default_file_template': self.canlog.default_filename_template
            },
            'appLog': {
                'log_dir': self.appLog.log_dir,
                'log_level': self.appLog.log_level,
                'log_to_console': self.appLog.log_to_console,
                'log_to_file': self.appLog.log_to_file,
                'max_log_file_size_mb': self.appLog.max_log_file_size_mb,
                'log_backup_count': self.appLog.log_backup_count,
                'log_format': self.appLog.log_format
            },
            'flask': {
                'host': self.flask.host,
                'port': self.flask.port,
                'debug': self.flask.debug,
                'enable_cors': self.flask.enable_cors
            }
        }

    def __repr__(self) -> str:
        return f"AppConfig(can={self.can}, log={self.canlog}, appLog={self.appLog}, flask={self.flask})"

# ============================================================================
# Example Usage
# ============================================================================

if __name__ == '__main__':
    # Default configuration
    print("=== Default Configuration ===")
    config = AppConfig()
    print(config)
    print(config.can)
    print(config.canlog)
    print(config.appLog)
    print(config.flask)
    print()
    
    # Load from environment
    print("=== Configuration from Environment ===")
    # Set some environment variables for demo
    os.environ['CAN_CHANNEL'] = 'can1'
    os.environ['CAN_BITRATE'] = '250000'
    os.environ['FLASK_PORT'] = '8080'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    env_config = AppConfig.from_env()
    print(env_config)
    print(env_config.can)
    print(env_config.canlog)
    print(env_config.appLog)
    print(env_config.flask)
    print()
    
    # Convert to dictionary
    print("=== Configuration as Dictionary ===")
    config_dict = env_config.to_dict()
    import json
    print(json.dumps(config_dict, indent=2))