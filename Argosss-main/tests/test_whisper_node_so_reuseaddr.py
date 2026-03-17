"""
Tests for whisper_node.py (root-level) — SO_REUSEADDR socket option added in this PR.
"""
import sys
import os
import socket
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWhisperNodeSocketOptions:
    """Verify that WhisperNode sets SO_REUSEADDR on its UDP socket."""

    def _make_mock_socket(self):
        """Return a mock socket that records setsockopt calls."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.setsockopt = MagicMock()
        mock_sock.bind = MagicMock()
        mock_sock.settimeout = MagicMock()
        return mock_sock

    def test_so_reuseaddr_is_set(self):
        mock_sock = self._make_mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            import importlib
            import whisper_node as wn
            importlib.reload(wn)
            wn.WhisperNode(
                node_id="test-reuseaddr",
                host="127.0.0.1",
                port=0,
                hidden_size=3,
                light_mode=True,
                enable_budding=False,
            )

        # Collect all setsockopt calls
        calls = mock_sock.setsockopt.call_args_list
        so_reuseaddr_calls = [
            c for c in calls
            if c.args == (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ]
        assert len(so_reuseaddr_calls) >= 1, (
            "WhisperNode must call setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)"
        )

    def test_so_broadcast_is_set(self):
        """SO_BROADCAST should still be set (pre-existing behaviour)."""
        mock_sock = self._make_mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            import importlib
            import whisper_node as wn
            importlib.reload(wn)
            wn.WhisperNode(
                node_id="test-broadcast",
                host="127.0.0.1",
                port=0,
                hidden_size=3,
                light_mode=True,
                enable_budding=False,
            )

        calls = mock_sock.setsockopt.call_args_list
        so_broadcast_calls = [
            c for c in calls
            if c.args == (socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        ]
        assert len(so_broadcast_calls) >= 1, (
            "WhisperNode must call setsockopt(SOL_SOCKET, SO_BROADCAST, 1)"
        )

    def test_so_reuseaddr_set_before_so_broadcast(self):
        """SO_REUSEADDR must be set before SO_BROADCAST (order matters for port reuse)."""
        mock_sock = self._make_mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            import importlib
            import whisper_node as wn
            importlib.reload(wn)
            wn.WhisperNode(
                node_id="test-order",
                host="127.0.0.1",
                port=0,
                hidden_size=3,
                light_mode=True,
                enable_budding=False,
            )

        calls = mock_sock.setsockopt.call_args_list
        option_sequence = [c.args[1] for c in calls]
        assert socket.SO_REUSEADDR in option_sequence
        assert socket.SO_BROADCAST in option_sequence
        reuseaddr_idx = option_sequence.index(socket.SO_REUSEADDR)
        broadcast_idx = option_sequence.index(socket.SO_BROADCAST)
        assert reuseaddr_idx < broadcast_idx, (
            "SO_REUSEADDR should be set before SO_BROADCAST"
        )

    def test_node_attributes_after_init(self):
        """Basic sanity: node attributes are set correctly after __init__."""
        mock_sock = self._make_mock_socket()
        with patch("socket.socket", return_value=mock_sock):
            import importlib
            import whisper_node as wn
            importlib.reload(wn)
            node = wn.WhisperNode(
                node_id="test-attrs",
                host="127.0.0.1",
                port=9876,
                hidden_size=4,
                light_mode=True,
                enable_budding=False,
            )

        assert node.node_id == "test-attrs"
        assert node.port == 9876
        assert node.host == "127.0.0.1"
        assert node.hidden_size == 4
        assert node.light_mode is True
        assert node.running is False