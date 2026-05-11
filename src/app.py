from pathlib import Path

import ipaddress
import logging_config
import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import signal
import socket
import sys
import threading

from config import AppConfig
from logging_config import setup_logging, get_logger
from can_interface import CANInterface
from dbc_manager import DBCManager
from session_manager import SessionManager
from hardware_manager import HardwareManager
from api.routes import register_routes


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

MDNS_HOST_ENV_VAR = "MDNS_ADVERTISE_HOST"
MDNS_RETRY_INTERVAL_SECONDS = 5

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
            success = self.dbc_manager.load_dbc(str(dbc_files[0].name))
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

        # Hardware Manager
        self.hardware_manager = HardwareManager(
            self.config.hardware,
            self.session_manager
        )

        # ZMQ Live Stream Listener
        if self.config.zmq.enabled:
            try:
                from stream_listener import ZmqStreamListener
                self.stream_listener = ZmqStreamListener(port=self.config.zmq.port)
                logger.info(f"ZMQ stream listener initialized on port {self.config.zmq.port} (waiting for CAN connection)")
            except ImportError:
                logger.error("pyzmq is not installed. Run `uv add pyzmq` to enable live streaming.")
                self.stream_listener = None
            except Exception as e:
                logger.error(f"Failed to initialize ZMQ stream listener: {e}")
                self.stream_listener = None
        else:
            self.stream_listener = None
            logger.info("ZMQ stream listener is disabled in config")

        # Flask App
        self.flask_app = Flask(__name__)
        CORS(self.flask_app)

        # Register routes
        register_routes(
            self.flask_app,
            self.session_manager,
            self.dbc_manager,
            self.config.canlog,
            self.config,
        )
        logger.info("API routes registered")

        self.zeroconf = None
        self.mdns_info = None
        self._mdns_retry_stop = threading.Event()
        self._mdns_retry_lock = threading.Lock()
        self._mdns_retry_thread = None
        self._register_mdns_service()

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
            if not self.can_interface.is_connected():
                self.can_interface.connect()
            
            # Attach the ZMQ listener now that CAN is connected
            if getattr(self, 'stream_listener', None):
                self.can_interface.add_listener(self.stream_listener)
                logger.info("ZMQ stream listener attached to active CAN interface")

            self.can_interface.send_message(
                self.can_interface.config.daq_messages['standby']
            )

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
            self._stop_mdns_retry()

            # Stop hardware manager
            if getattr(self, 'hardware_manager', None):
                logger.info("Cleaning up hardware controls...")
                self.hardware_manager.cleanup()

            # Stop any active session
            if self.session_manager.is_active():
                logger.info("Stopping active session...")
                self.session_manager.stop()

            # Stop the ZMQ stream
            if hasattr(self, 'stream_listener') and self.stream_listener:
                logger.info("Stopping ZMQ stream...")
                self.stream_listener.stop()

            if self.zeroconf and self.mdns_info:
                logger.info("Stopping mDNS advertisement...")
                self.zeroconf.unregister_service(self.mdns_info)
                self.zeroconf.close()
                self.zeroconf = None
                self.mdns_info = None

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

    def _register_mdns_service(self):
        """Advertise the DAQ Flask API over mDNS when the dependency is available."""
        if self.zeroconf and self.mdns_info:
            return True

        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError:
            logger.warning("zeroconf is not installed. mDNS discovery is disabled.")
            return False
        except Exception as e:
            logger.warning(f"Unable to import zeroconf: {e}")
            return False

        address = self._resolve_lan_ip()
        if not address:
            logger.warning(
                f"Could not resolve a LAN IP for mDNS advertisement. "
                f"Retrying in {MDNS_RETRY_INTERVAL_SECONDS} seconds."
            )
            self._ensure_mdns_retry_thread()
            return False

        service_type = "_wolftrack-daq._tcp.local."
        service_name = f"{socket.gethostname()} {self.config.can.channel}.{service_type}"
        properties = {
            b"api_version": b"1",
            b"stream_endpoint_path": b"/api/stream-endpoint",
        }

        try:
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            self.mdns_info = ServiceInfo(
                type_=service_type,
                name=service_name,
                addresses=[socket.inet_aton(address)],
                port=self.config.flask.port,
                properties=properties,
                server=f"{socket.gethostname()}.local.",
            )
            self.zeroconf.register_service(self.mdns_info)
            logger.info(f"mDNS service registered at {address}:{self.config.flask.port}")
            return True
        except Exception as e:
            logger.warning(f"Failed to register mDNS service: {e}")
            if self.zeroconf:
                self.zeroconf.close()
            self.zeroconf = None
            self.mdns_info = None
            self._ensure_mdns_retry_thread()
            return False

    def _resolve_lan_ip(self) -> str | None:
        override = os.getenv(MDNS_HOST_ENV_VAR, "").strip()
        if override:
            if self._is_usable_ipv4(override):
                return override

            logger.warning(
                f"{MDNS_HOST_ENV_VAR} is set to '{override}' but is not a usable IPv4 address "
                "for mDNS advertisement."
            )

        interface_addresses = self._get_active_interface_addresses()
        preferred_order = {"wlan0": 0, "eth0": 1}
        interface_addresses.sort(key=lambda item: (preferred_order.get(item[0], 2), item[0]))

        for _name, address in interface_addresses:
            if self._is_usable_ipv4(address):
                return address

        return self._resolve_udp_route_ip()

    def _get_active_interface_addresses(self) -> list[tuple[str, str]]:
        try:
            interface_names = [name for _index, name in socket.if_nameindex()]
        except (AttributeError, OSError):
            return []

        interface_addresses: list[tuple[str, str]] = []
        for interface_name in interface_names:
            if not self._is_interface_up(interface_name):
                continue

            address = self._get_interface_ipv4_address(interface_name)
            if self._is_usable_ipv4(address):
                interface_addresses.append((interface_name, address))

        return interface_addresses

    def _is_interface_up(self, interface_name: str) -> bool:
        try:
            import fcntl
            import struct
        except ImportError:
            return True

        request = struct.pack("256s", interface_name.encode("utf-8")[:15])
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            result = fcntl.ioctl(probe.fileno(), 0x8913, request)
            flags = struct.unpack("H", result[16:18])[0]
            return bool(flags & 0x1)
        except OSError:
            return False
        finally:
            probe.close()

    def _get_interface_ipv4_address(self, interface_name: str) -> str | None:
        try:
            import fcntl
            import struct
        except ImportError:
            return None

        request = struct.pack("256s", interface_name.encode("utf-8")[:15])
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            return socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24])
        except OSError:
            return None
        finally:
            probe.close()

    def _resolve_udp_route_ip(self) -> str | None:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            return address if self._is_usable_ipv4(address) else None
        except OSError:
            return None
        finally:
            probe.close()

    def _ensure_mdns_retry_thread(self):
        if self._mdns_retry_stop.is_set():
            return

        with self._mdns_retry_lock:
            if self._mdns_retry_thread and self._mdns_retry_thread.is_alive():
                return

            self._mdns_retry_thread = threading.Thread(
                target=self._mdns_retry_worker,
                name="wolftrack-mdns-retry",
                daemon=True,
            )
            self._mdns_retry_thread.start()

    def _mdns_retry_worker(self):
        while not self._mdns_retry_stop.wait(MDNS_RETRY_INTERVAL_SECONDS):
            if self.zeroconf and self.mdns_info:
                return

            logger.info("Retrying mDNS advertisement...")
            if self._register_mdns_service():
                return

    def _stop_mdns_retry(self):
        retry_stop = getattr(self, "_mdns_retry_stop", None)
        if retry_stop is None:
            return

        retry_stop.set()
        retry_thread = getattr(self, "_mdns_retry_thread", None)
        if retry_thread and retry_thread.is_alive() and retry_thread is not threading.current_thread():
            retry_thread.join(timeout=1)

        self._mdns_retry_thread = None

    @staticmethod
    def _is_usable_ipv4(address: str | None) -> bool:
        if not address:
            return False

        try:
            ip = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError:
            return False

        return not (ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified)


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
