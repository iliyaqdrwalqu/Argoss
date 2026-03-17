import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectivity.whisper_node import WhisperNode


class TestWhisperNode(unittest.TestCase):
    def setUp(self):
        self.node = WhisperNode(
            node_id="test-node",
            port=0,
            hidden_size=3,
            light_mode=True,
            enable_budding=False,
        )

    def tearDown(self):
        self.node.stop()

    def test_dispatch_state_message_updates_inbox(self):
        self.node._dispatch({"type": self.node.MT_STATE, "node_id": "peer-1", "state": [0.1, 0.2, 0.3]})
        self.assertEqual(len(self.node.inbox_states), 1)
        peer, vec = self.node.inbox_states[0]
        self.assertEqual(peer, "peer-1")
        self.assertEqual(vec.shape[0], 3)

    def test_observe_broadcasts_state(self):
        self.node.inbox_states.append(("peer-1", np.array([0.3, 0.1, 0.2])))
        sent = []

        with patch("src.connectivity.whisper_node.np.random.randn", return_value=0.0), \
             patch("src.connectivity.whisper_node.np.random.rand", return_value=1.0), \
             patch.object(self.node, "_broadcast", side_effect=lambda msg: sent.append(msg)):
            self.node.observe()

        self.assertGreaterEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], self.node.MT_STATE)
        self.assertIn("state", sent[0])
        self.assertEqual(len(sent[0]["state"]), 3)
        self.assertIsInstance(self.node.last_silence, float)

    def test_observe_applies_mimic_weights(self):
        weights = {
            "W_h": np.ones((3, 3)).tolist(),
            "W_i": np.ones((3, 1)).tolist(),
            "b": np.ones(3).tolist(),
        }
        self.node.inbox_mimic_data["peer-2"] = weights

        with patch("src.connectivity.whisper_node.np.random.randn", return_value=0.0), \
             patch("src.connectivity.whisper_node.np.random.rand", return_value=1.0), \
             patch.object(self.node, "_broadcast", return_value=None):
            self.node.observe()

        self.assertTrue(np.array_equal(self.node.rnn.W_h, np.ones((3, 3))))
        self.assertTrue(np.array_equal(self.node.rnn.W_i, np.ones((3, 1))))
        self.assertTrue(np.array_equal(self.node.rnn.b, np.ones(3)))

