from src.interface import kivy_ma
from src.interface.web_engine import HTML_TEMPLATE


def test_kivy_ma_process_all_returns_exec_prefix():
    node = kivy_ma.SovereignNode(core=None)
    assert node.process_all("root") == "Exec: root"


def test_kivy_ma_keeps_backward_compatible_alias():
    assert kivy_ma.SovereignNodeMA is kivy_ma.SovereignNode


def test_web_engine_template_contains_master_header():
    assert "ARGOS v1.33 MASTER" in HTML_TEMPLATE
    assert "NODE_ID: Master_7F2A | STATUS: ONLINE" in HTML_TEMPLATE
    assert "ARGOS v1.33 ONLINE" in HTML_TEMPLATE


def test_web_engine_template_contains_omni_presence_standard_blocks():
    assert "DESKTOP MASTER" in HTML_TEMPLATE
    assert "PHONE NODE" in HTML_TEMPLATE
    assert "WEARABLE" in HTML_TEMPLATE
    assert "WEB PORTAL" in HTML_TEMPLATE
    assert "SWARM METRICS" in HTML_TEMPLATE
    assert "TAP TO SYNC" in HTML_TEMPLATE
    assert "STABLE" in HTML_TEMPLATE
    assert "C2 OVERRIDE" in HTML_TEMPLATE
