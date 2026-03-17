"""Tests for industrial_protocols.py integration."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industrial_protocols import (
    IndustrialProtocolsManager,
    IndustrialDevice,
    ProtocolType,
    KNXBridge,
    LonWorksBridge,
    MBusBridge,
    OPCUABridge,
)


def test_manager_init():
    mgr = IndustrialProtocolsManager()
    assert mgr.knx is not None
    assert mgr.lon is not None
    assert mgr.mbus is not None
    assert mgr.opcua is not None


def test_manager_status_returns_string():
    mgr = IndustrialProtocolsManager()
    result = mgr.status()
    assert isinstance(result, str)
    assert len(result) > 0


def test_handle_command_status():
    mgr = IndustrialProtocolsManager()
    result = mgr.handle_command("industrial статус")
    assert isinstance(result, str)
    assert len(result) > 0


def test_handle_command_промышленные_протоколы():
    mgr = IndustrialProtocolsManager()
    result = mgr.handle_command("промышленные протоколы")
    assert isinstance(result, str)


def test_handle_command_discovery():
    mgr = IndustrialProtocolsManager()
    result = mgr.handle_command("industrial discovery")
    assert isinstance(result, str)
    assert "Discovery" in result or "discovery" in result.lower() or "устройств" in result


def test_handle_command_devices_empty():
    mgr = IndustrialProtocolsManager()
    result = mgr.handle_command("industrial устройства")
    assert isinstance(result, str)
    # With no active connections, expect "no devices found" message
    assert "устройств" in result or "не найдено" in result


def test_read_unknown_protocol():
    mgr = IndustrialProtocolsManager()
    result = mgr.read("unknown", "addr")
    assert isinstance(result, dict)
    assert "error" in result


def test_write_unknown_protocol():
    mgr = IndustrialProtocolsManager()
    result = mgr.write("unknown", "addr", 42)
    assert isinstance(result, str)
    assert "Unknown" in result or "❌" in result


def test_read_knx():
    mgr = IndustrialProtocolsManager()
    result = mgr.read("knx", "1/1/1")
    assert isinstance(result, dict)


def test_read_mbus():
    mgr = IndustrialProtocolsManager()
    result = mgr.read("mbus", "1")
    assert isinstance(result, dict)


def test_read_opcua():
    mgr = IndustrialProtocolsManager()
    result = mgr.read("opcua", "ns=0;i=84")
    assert isinstance(result, dict)


def test_all_devices_empty():
    mgr = IndustrialProtocolsManager()
    devices = mgr.all_devices()
    assert isinstance(devices, list)


def test_industrial_device_to_dict():
    dev = IndustrialDevice(
        protocol=ProtocolType.KNX,
        device_id="dev1",
        name="Light",
        address="1/1/1",
    )
    d = dev.to_dict()
    assert d["protocol"] == "knx"
    assert d["device_id"] == "dev1"
    assert d["name"] == "Light"
    assert d["address"] == "1/1/1"


def test_core_integration():
    """Test that IndustrialProtocolsManager integrates with a mock core."""
    from types import SimpleNamespace
    core = SimpleNamespace()
    mgr = IndustrialProtocolsManager(core=core)
    assert mgr.core is core


def test_knx_bridge_connect():
    knx = KNXBridge()
    result = knx.connect("192.168.1.1")
    assert isinstance(result, str)


def test_lonworks_bridge_scan():
    lon = LonWorksBridge()
    result = lon.discover(timeout=0.1)
    assert isinstance(result, list)


def test_mbus_bridge_scan():
    mbus = MBusBridge()
    result = mbus.discover(addr_from=0, addr_to=0)
    assert isinstance(result, list)


def test_opcua_bridge_connect():
    opcua = OPCUABridge()
    result = opcua.connect("opc.tcp://localhost:4840")
    assert isinstance(result, str)
