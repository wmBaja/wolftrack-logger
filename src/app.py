from pathlib import Path

import logging_config
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import signal
import sys

from src.config import AppConfig
from src.logging_config import setup_logging, get_logger
from src.can_interface import CANInterface
from src.dbc_manager import DBCManager
from src.session_manager import SessionManager
from src.api.routes import register_routes


# Load .env file (do this BEFORE importing config)
load_dotenv()

# Now import config - it will use environment variables
# Create configuration from environment
config = AppConfig.from_env()

# Setup logging based on loaded configuration
logger = logging_config.setup_logging(config.appLog.log_dir,
                                      config.appLog.log_level,
                                      config.appLog.log_to_console,
                                      config.appLog.log_to_file,
                                      config.appLog.max_log_file_size_mb,
                                      config.appLog.log_backup_count,
                                      config.appLog.log_format)

class CANLoggerApp:
    """
    Main CAN Logger Application.

    Initializes and manages all components:
    - Flask web server
    - CAN interface
    - DBC manager
    - Session manager
    """

    def __init__(self):
        """Initialize the application"""
        logger.info("="*70)
        logger.info("CAN Logger Backend Starting...")
        logger.info("="*70)

        # Load configuration
        self.config = AppConfig.from_env()
        logger.info(f"Configuration loaded")
        logger.info(f"  CAN Channel: {self.config.can.channel}")
        logger.info(f"  CAN Bitrate: {self.config.can.bitrate}")
        logger.info(f"  Output Dir: {self.config.canlog.output_dir}")

        # Initialize components
        logger.info("Initializing components...")

        # CAN Interface
        self.can_interface = CANInterface(self.config.can)

        # DBC Manager
        self.dbc_manager = DBCManager(self.config.canlog.dbc_dir)

        # Try to auto-load DBCs from directory
        dbc_path = Path(self.config.canlog.dbc_dir)
        dbc_files = list(dbc_path.glob('*.dbc')) if dbc_path.exists() else []
        if dbc_files:
            logger.info(f"Found {len(dbc_files)} DBC file(s)")
            # Load first DBC file found
            success = self.dbc_manager.load_dbc(str(dbc_files[0]))
            if success:
                logger.info(f"Loaded DBC: {self.dbc_manager.dbc_name}")
            else:
                logger.warning(f"Failed to load DBC: {dbc_files[0]}")
        else:
            logger.info("No DBC files found (optional)")

        # Session Manager
        self.session_manager = SessionManager(
            self.can_interface,
            self.dbc_manager,
            self.config.canlog
        )

        # Flask App
        self.flask_app = Flask(__name__)
        CORS(self.flask_app)

        # Register routes
        register_routes(
            self.flask_app,
            self.session_manager,
            self.dbc_manager,
            self.config.canlog
        )
        logger.info("API routes registered")

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("="*70)
        logger.info("Initialization complete")
        logger.info("="*70)

    def run(self):
        """Run the Flask application"""
        logger.info(f"Starting Flask server on {self.config.flask.host}:{self.config.flask.port}")
        logger.info(f"Debug mode: {self.config.flask.debug}")
        logger.info("Press Ctrl+C to stop")
        logger.info("="*70)

        try:
            self.flask_app.run(
                host=self.config.flask.host,
                port=self.config.flask.port,
                debug=self.config.flask.debug,
                threaded=True
            )
        except Exception as e:
            logger.error(f"Error running Flask app: {e}", exc_info=True)
            self.cleanup()
            sys.exit(1)

    def cleanup(self):
        """Cleanup resources on shutdown"""
        logger.info("")
        logger.info("="*70)
        logger.info("Shutting down...")
        logger.info("="*70)

        try:
            # Stop any active session
            if self.session_manager.is_active():
                logger.info("Stopping active session...")
                self.session_manager.stop()

            # Disconnect CAN interface
            if self.can_interface.is_connected():
                logger.info("Disconnecting CAN interface...")
                self.can_interface.disconnect()

            logger.info("Cleanup complete")
            logger.info("="*70)

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals (Ctrl+C, SIGTERM)"""
        logger.info("")
        logger.info("Received shutdown signal")
        self.cleanup()
        sys.exit(0)


def create_app():
    """
    Flask application factory.

    Returns:
        Flask application instance
    """
    load_dotenv()
    setup_logging(log_level='INFO')

    app_instance = CANLoggerApp()
    return app_instance.flask_app


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    try:
        app = CANLoggerApp()
        app.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
