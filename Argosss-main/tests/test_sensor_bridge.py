import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectivity.sensor_bridge import ArgosSensorBridge


class TestSensorBridgeInternetCheck(unittest.TestCase):
    def test_ping_status_online(self):
        bridge = ArgosSensorBridge()
        conn = MagicMock()
        conn.__enter__.return_value = conn

        with patch("src.connectivity.sensor_bridge.socket.create_connection", return_value=conn) as cc, \
             patch("src.connectivity.sensor_bridge.time.time", side_effect=[100.0, 100.05]):
            status = bridge._ping_status()

        cc.assert_called_once_with(("8.8.8.8", 53), timeout=2)
        self.assertTrue(status["ping"].endswith("ms"))
        self.assertEqual(status["status"], "Stable")

    def test_ping_status_offline(self):
        bridge = ArgosSensorBridge()
        with patch("src.connectivity.sensor_bridge.socket.create_connection", side_effect=OSError):
            status = bridge._ping_status()

        self.assertEqual(status, {"ping": "inf", "status": "Offline"})
