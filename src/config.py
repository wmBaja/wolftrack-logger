"""
Configuration module for CAN Logger Backend
src/config.py

Defines all configuration dataclasses and loading methods.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


@dataclass
class CANConfig:
    """CAN bus hardware configuration"""
    
    interface: str = 'socketcan'
    channel: str = 'can0'
    bitrate: int = 500000
    fd: bool = True  # CAN-FD support
    data_bitrate: int = 2000000  # CAN-FD data phase bitrate
    
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
    
    def __repr__(self) -> str:
        return (f"CANConfig(interface={self.interface}, channel={self.channel}, "
                f"bitrate={self.bitrate}, fd={self.fd}, data_bitrate={self.data_bitrate})")


@dataclass
class LogConfig:
    """MDF4 logging configuration"""
    
    output_dir: str = './logs'
    dbc_dir: str = './dbc'
    max_file_size_mb: int = 100
    compression: int = 2  # MDF4 compression level (0=none, 1=deflate, 2=transposition+deflate)
    buffer_size: int = 10000  # Message queue size
    
    @classmethod
    def from_env(cls) -> 'LogConfig':
        """Load configuration from environment variables"""
        return cls(
            output_dir=os.getenv('LOG_OUTPUT_DIR', './logs'),
            dbc_dir=os.getenv('DBC_DIR', './dbc_files'),
            max_file_size_mb=int(os.getenv('LOG_MAX_FILE_SIZE_MB', '100')),
            compression=int(os.getenv('LOG_COMPRESSION', '2')),
            buffer_size=int(os.getenv('LOG_BUFFER_SIZE', '10000'))
        )
    
    def __post_init__(self):
        """Create directories if they don't exist"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.dbc_dir).mkdir(parents=True, exist_ok=True)
    
    def __repr__(self) -> str:
        return (f"LogConfig(output_dir={self.output_dir}, dbc_dir={self.dbc_dir}, "
                f"compression={self.compression})")


@dataclass
class AppConfig:
    """Main application configuration"""
    
    can: CANConfig = field(default_factory=CANConfig)
    log: LogConfig = field(default_factory=LogConfig)
    host: str = '0.0.0.0'
    port: int = 5000
    debug: bool = False
    log_level: str = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Load entire configuration from environment variables"""
        return cls(
            can=CANConfig.from_env(),
            log=LogConfig.from_env(),
            host=os.getenv('FLASK_HOST', '0.0.0.0'),
            port=int(os.getenv('FLASK_PORT', '5000')),
            debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
            log_level=os.getenv('LOG_LEVEL', 'INFO').upper()
        )
    
    @classmethod
    def from_dict(cls, config_dict: dict) -> 'AppConfig':
        """Load configuration from dictionary (for config files)"""
        can_config = CANConfig(**config_dict.get('can', {}))
        log_config = LogConfig(**config_dict.get('log', {}))
        
        return cls(
            can=can_config,
            log=log_config,
            host=config_dict.get('host', '0.0.0.0'),
            port=config_dict.get('port', 5000),
            debug=config_dict.get('debug', False),
            log_level=config_dict.get('log_level', 'INFO').upper()
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
                'output_dir': self.log.output_dir,
                'dbc_dir': self.log.dbc_dir,
                'max_file_size_mb': self.log.max_file_size_mb,
                'compression': self.log.compression,
                'buffer_size': self.log.buffer_size
            },
            'host': self.host,
            'port': self.port,
            'debug': self.debug,
            'log_level': self.log_level
        }
    
    def __repr__(self) -> str:
        return (f"AppConfig(host={self.host}, port={self.port}, "
                f"debug={self.debug}, log_level={self.log_level})")


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == '__main__':
    # Default configuration
    print("=== Default Configuration ===")
    config = AppConfig()
    print(config)
    print(config.can)
    print(config.log)
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
    print()
    
    # Convert to dictionary
    print("=== Configuration as Dictionary ===")
    config_dict = env_config.to_dict()
    import json
    print(json.dumps(config_dict, indent=2))