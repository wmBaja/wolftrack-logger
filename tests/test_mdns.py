import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import app


class FakeServiceInfo:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeZeroconf:
    instances = []

    def __init__(self, ip_version):
        self.ip_version = ip_version
        self.registered = []
        self.unregistered = []
        self.closed = False
        FakeZeroconf.instances.append(self)

    def register_service(self, info):
        self.registered.append(info)

    def unregister_service(self, info):
        self.unregistered.append(info)

    def close(self):
        self.closed = True


class FakeIPVersion:
    V4Only = object()


def build_logger_app():
    logger_app = object.__new__(app.CANLoggerApp)
    logger_app.config = SimpleNamespace(
        can=SimpleNamespace(channel="can0"),
        flask=SimpleNamespace(port=5500),
    )
    logger_app.zeroconf = None
    logger_app.mdns_info = None
    logger_app._mdns_retry_stop = threading.Event()
    logger_app._mdns_retry_lock = threading.Lock()
    logger_app._mdns_retry_thread = None
    return logger_app


def install_fake_zeroconf(monkeypatch):
    FakeZeroconf.instances = []
    fake_module = SimpleNamespace(
        IPVersion=FakeIPVersion,
        ServiceInfo=FakeServiceInfo,
        Zeroconf=FakeZeroconf,
    )
    monkeypatch.setitem(sys.modules, "zeroconf", fake_module)


def test_resolve_lan_ip_prefers_env_override(monkeypatch):
    logger_app = build_logger_app()
    monkeypatch.setenv(app.MDNS_HOST_ENV_VAR, "10.42.0.99")
    monkeypatch.setattr(logger_app, "_get_active_interface_addresses", lambda: [("wlan0", "10.42.0.1")])
    monkeypatch.setattr(logger_app, "_resolve_udp_route_ip", lambda: "192.168.1.50")

    assert logger_app._resolve_lan_ip() == "10.42.0.99"


def test_resolve_lan_ip_prefers_wlan0_over_eth0(monkeypatch):
    logger_app = build_logger_app()
    monkeypatch.delenv(app.MDNS_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(
        logger_app,
        "_get_active_interface_addresses",
        lambda: [("eth0", "192.168.1.20"), ("wlan0", "10.42.0.1"), ("usb0", "192.168.50.2")],
    )
    monkeypatch.setattr(logger_app, "_resolve_udp_route_ip", lambda: None)

    assert logger_app._resolve_lan_ip() == "10.42.0.1"


def test_resolve_lan_ip_prefers_eth0_when_wlan0_missing(monkeypatch):
    logger_app = build_logger_app()
    monkeypatch.delenv(app.MDNS_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(
        logger_app,
        "_get_active_interface_addresses",
        lambda: [("usb0", "192.168.50.2"), ("eth0", "192.168.1.20")],
    )
    monkeypatch.setattr(logger_app, "_resolve_udp_route_ip", lambda: None)

    assert logger_app._resolve_lan_ip() == "192.168.1.20"


def test_resolve_lan_ip_ignores_only_loopback_addresses(monkeypatch):
    logger_app = build_logger_app()
    monkeypatch.delenv(app.MDNS_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(
        logger_app,
        "_get_active_interface_addresses",
        lambda: [("lo", "127.0.0.1"), ("wlan0", "169.254.10.20")],
    )
    monkeypatch.setattr(logger_app, "_resolve_udp_route_ip", lambda: None)

    assert logger_app._resolve_lan_ip() is None


def test_resolve_lan_ip_uses_udp_fallback_when_no_interface_address_exists(monkeypatch):
    logger_app = build_logger_app()
    monkeypatch.delenv(app.MDNS_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(logger_app, "_get_active_interface_addresses", lambda: [])
    monkeypatch.setattr(logger_app, "_resolve_udp_route_ip", lambda: "192.168.8.2")

    assert logger_app._resolve_lan_ip() == "192.168.8.2"


def test_register_mdns_service_succeeds_on_first_attempt(monkeypatch):
    install_fake_zeroconf(monkeypatch)
    logger_app = build_logger_app()
    monkeypatch.setattr(logger_app, "_resolve_lan_ip", lambda: "10.42.0.1")

    assert logger_app._register_mdns_service() is True
    assert logger_app.zeroconf is FakeZeroconf.instances[0]
    assert logger_app.zeroconf.registered == [logger_app.mdns_info]
    assert logger_app.mdns_info.kwargs["port"] == 5500
    assert logger_app.mdns_info.kwargs["addresses"] == [app.socket.inet_aton("10.42.0.1")]


def test_register_mdns_service_retries_until_ip_is_available(monkeypatch):
    install_fake_zeroconf(monkeypatch)
    logger_app = build_logger_app()
    monkeypatch.setattr(app, "MDNS_RETRY_INTERVAL_SECONDS", 0.01)

    addresses = iter([None, "10.42.0.1"])
    monkeypatch.setattr(logger_app, "_resolve_lan_ip", lambda: next(addresses, "10.42.0.1"))

    assert logger_app._register_mdns_service() is False

    deadline = time.time() + 1
    while time.time() < deadline and logger_app.mdns_info is None:
        time.sleep(0.01)

    logger_app._stop_mdns_retry()

    assert logger_app.mdns_info is not None
    assert logger_app.zeroconf.registered == [logger_app.mdns_info]


def test_cleanup_stops_retry_thread_and_unregisters_mdns(monkeypatch):
    install_fake_zeroconf(monkeypatch)
    logger_app = build_logger_app()
    monkeypatch.setattr(logger_app, "_resolve_lan_ip", lambda: "10.42.0.1")
    logger_app._register_mdns_service()
    zeroconf = logger_app.zeroconf
    mdns_info = logger_app.mdns_info

    logger_app.hardware_manager = SimpleNamespace(cleanup=Mock())
    logger_app.session_manager = SimpleNamespace(is_active=lambda: False, stop=Mock())
    logger_app.stream_listener = SimpleNamespace(stop=Mock())
    logger_app.can_interface = SimpleNamespace(is_connected=lambda: False, disconnect=Mock())

    def wait_for_stop():
        logger_app._mdns_retry_stop.wait(1)

    logger_app._mdns_retry_thread = threading.Thread(target=wait_for_stop, daemon=True)
    logger_app._mdns_retry_thread.start()

    logger_app.cleanup()

    assert logger_app._mdns_retry_stop.is_set()
    assert logger_app._mdns_retry_thread is None
    assert zeroconf.unregistered == [mdns_info]
    assert zeroconf.closed is True
    assert logger_app.zeroconf is None
