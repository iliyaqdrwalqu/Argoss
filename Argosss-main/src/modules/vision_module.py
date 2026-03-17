from src.modules.base import BaseModule


class VisionModule(BaseModule):
    module_id = "vision"
    title = "Vision"

    def can_handle(self, text: str, lowered: str) -> bool:
        keys = ["посмотри на экран", "что на экране", "скриншот", "посмотри в камеру", "что видит камера", "включи камеру", "проанализируй изображение", "анализ фото"]
        return any(k in lowered for k in keys)

    def handle(self, text: str, lowered: str, admin=None, flasher=None) -> str | None:
        if not self.core or not self.core.vision:
            return None

        if any(k in lowered for k in ["посмотри на экран", "что на экране", "скриншот"]):
            question = text.replace("аргос", "").replace("посмотри на экран", "").replace("что на экране", "").replace("скриншот", "").strip()
            return self.core.vision.look_at_screen(question or "Что происходит на экране?")

        if any(k in lowered for k in ["посмотри в камеру", "что видит камера", "включи камеру"]):
            question = text.replace("аргос", "").replace("посмотри в камеру", "").replace("что видит камера", "").strip()
            return self.core.vision.look_through_camera(question or "Что ты видишь?")

        if "проанализируй изображение" in lowered or "анализ фото" in lowered:
            path = text.split()[-1]
            return self.core.vision.analyze_file(path)

        return None
