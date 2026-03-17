import unittest

from src.factory.flasher import AirFlasher


class TestWearableFirmwareMod(unittest.TestCase):
    def test_workflow_includes_avatar_and_decompile_fallback(self):
        text = AirFlasher().wearable_firmware_mod(
            device="Argos Band X",
            avatar="sigtrip",
            include_4pda=False,
        )
        self.assertIn("avatar: sigtrip", text)
        self.assertIn("Если оригинал не найден", text)
        self.assertIn("Дизассемблировать/проанализировать локальный образ", text)

    def test_workflow_can_include_4pda_source_and_port_hint(self):
        text = AirFlasher().wearable_firmware_mod(
            device="Argos Ring",
            port="/dev/ttyUSB0",
            include_4pda=True,
        )
        self.assertIn("4pda", text.lower())
        self.assertIn("умная прошивка /dev/ttyUSB0", text)

    def test_android_argos_os_plan_phone_preserves_core_features(self):
        text = AirFlasher().android_argos_os_plan(profile="phone", preserve_features=True)
        self.assertIn("Argos OS Android Plan (phone)", text)
        self.assertIn("телефония/SMS", text)
        self.assertIn("Режим сохранения функций включён", text)

    def test_android_argos_os_plan_tv_profile(self):
        text = AirFlasher().android_argos_os_plan(profile="tv", preserve_features=True)
        self.assertIn("Argos OS Android Plan (tv)", text)
        self.assertIn("HDMI-CEC", text)


if __name__ == "__main__":
    unittest.main()
