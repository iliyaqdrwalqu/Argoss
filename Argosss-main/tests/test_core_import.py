import unittest


class TestCoreImport(unittest.TestCase):
    def test_src_core_exports_argoscore(self):
        from src.core import ArgosCore

        self.assertEqual(ArgosCore.__name__, "ArgosCore")
