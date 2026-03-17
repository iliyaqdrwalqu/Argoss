import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectivity.max_bridge import MaxBridge
from src.connectivity.messenger_router import MessengerRouter
from src.connectivity.slack_bridge import SlackBridge
from src.connectivity.whatsapp_bridge import WhatsAppBridge


class _DummyResponse:
    def __init__(self, payload=None, fail=False):
        self._payload = payload or {}
        self._fail = fail

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._fail:
            raise RuntimeError("http_error")


class TestWhatsAppBridge(unittest.TestCase):
    def test_whatsapp_cloud_success(self):
        bridge = WhatsAppBridge(cloud_token="token", phone_number_id="12345")
        with patch(
            "src.connectivity.whatsapp_bridge.requests.post",
            return_value=_DummyResponse({"messages": [{"id": "wamid.1"}]}),
        ) as post:
            result = bridge.send_message("+70000000000", "hello")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "whatsapp_cloud")
        post.assert_called_once()

    def test_whatsapp_fallback_to_twilio(self):
        bridge = WhatsAppBridge(
            cloud_token="token",
            phone_number_id="12345",
            twilio_account_sid="sid",
            twilio_auth_token="auth",
            twilio_whatsapp_from="+19999999999",
        )

        with patch(
            "src.connectivity.whatsapp_bridge.requests.post",
            side_effect=[RuntimeError("cloud down"), _DummyResponse({"sid": "SM1"})],
        ):
            result = bridge.send_message("+70000000000", "fallback")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "twilio")


class TestSlackBridge(unittest.TestCase):
    def test_send_message_success(self):
        bridge = SlackBridge(bot_token="xoxb-token")
        with patch(
            "src.connectivity.slack_bridge.requests.post",
            return_value=_DummyResponse({"ok": True, "ts": "123.45"}),
        ):
            result = bridge.send_message(channel="#alerts", text="ping")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "slack")

    def test_socket_mode_ready(self):
        bridge = SlackBridge(bot_token="xoxb", app_token="xapp")
        self.assertTrue(bridge.socket_mode_ready())


class TestMaxBridge(unittest.TestCase):
    def test_send_message_success(self):
        bridge = MaxBridge(bot_token="max-token")
        with patch(
            "src.connectivity.max_bridge.requests.post",
            return_value=_DummyResponse({"ok": True, "result": {"message_id": 10}}),
        ) as post:
            result = bridge.send_message(chat_id="42", text="hello max")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "max")
        post.assert_called_once()


class TestMessengerRouter(unittest.TestCase):
    def test_routes_to_whatsapp(self):
        router = MessengerRouter()
        with patch.object(router.whatsapp, "send_message", return_value={"ok": True}) as sender:
            result = router.route_message("whatsapp", "+70000000000", "hi")

        sender.assert_called_once_with(to="+70000000000", text="hi")
        self.assertTrue(result["ok"])

    def test_routes_to_slack(self):
        router = MessengerRouter()
        with patch.object(router.slack, "send_message", return_value={"ok": True}) as sender:
            result = router.route_message("slack", "#alerts", "hi")

        sender.assert_called_once_with(channel="#alerts", text="hi")
        self.assertTrue(result["ok"])

    def test_routes_to_max(self):
        router = MessengerRouter()
        with patch.object(router.max, "send_message", return_value={"ok": True}) as sender:
            result = router.route_message("max", "42", "hi")

        sender.assert_called_once_with(chat_id="42", text="hi")
        self.assertTrue(result["ok"])

    def test_unsupported_messenger(self):
        router = MessengerRouter()
        result = router.route_message("unknown", "id", "hello")
        self.assertFalse(result["ok"])
