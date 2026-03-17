"""
icon_generator.py — Генератор иконок для Argos APK/приложения.
Создаёт иконки нужных размеров из базового изображения или SVG.
"""
import os
from pathlib import Path
from src.argos_logger import get_logger

log = get_logger("argos.icons")

ICON_SIZES = {
    "android": [48, 72, 96, 144, 192],
    "ios":     [29, 40, 57, 60, 76, 120, 180],
    "desktop": [16, 32, 48, 64, 128, 256],
    "web":     [16, 32, 96, 180, 192, 512],
}

DEFAULT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#1a1a2e" rx="80"/>
  <circle cx="256" cy="200" r="80" fill="none" stroke="#00d4ff" stroke-width="8"/>
  <circle cx="256" cy="200" r="20" fill="#00d4ff"/>
  <line x1="256" y1="280" x2="256" y2="380" stroke="#00d4ff" stroke-width="8"/>
  <line x1="256" y1="380" x2="200" y2="440" stroke="#00d4ff" stroke-width="8"/>
  <line x1="256" y1="380" x2="312" y2="440" stroke="#00d4ff" stroke-width="8"/>
  <line x1="256" y1="320" x2="200" y2="290" stroke="#00d4ff" stroke-width="8"/>
  <line x1="256" y1="320" x2="312" y2="290" stroke="#00d4ff" stroke-width="8"/>
  <text x="256" y="490" font-family="monospace" font-size="48" fill="#00d4ff"
        text-anchor="middle" font-weight="bold">ARGOS</text>
</svg>"""


class IconGenerator:
    def __init__(self, output_dir: str = "assets/icons"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_all(self, source_path: str = None, platform: str = "android") -> str:
        """Генерирует иконки всех размеров для платформы."""
        sizes = ICON_SIZES.get(platform, ICON_SIZES["android"])
        results = []

        try:
            from PIL import Image
            if source_path and os.path.exists(source_path):
                img = Image.open(source_path).convert("RGBA")
            else:
                img = self._create_default_pil_icon()

            for size in sizes:
                out = Path(self.output_dir) / f"icon_{size}x{size}.png"
                resized = img.resize((size, size), Image.LANCZOS)
                resized.save(str(out))
                results.append(f"{size}x{size}")
            log.info("IconGenerator: создано %d иконок для %s", len(sizes), platform)
            return f"✅ Иконки созданы ({platform}): {', '.join(results)}"
        except ImportError:
            return self._generate_svg_fallback(sizes)

    def _create_default_pil_icon(self):
        """Создаёт базовую иконку через PIL."""
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGBA", (512, 512), (26, 26, 46, 255))
        draw = ImageDraw.Draw(img)
        # Глаз Аргоса
        draw.ellipse([176, 120, 336, 280], outline=(0, 212, 255), width=8)
        draw.ellipse([236, 180, 276, 220], fill=(0, 212, 255))
        # Тело
        draw.line([(256, 280), (256, 380)], fill=(0, 212, 255), width=8)
        draw.line([(256, 380), (200, 440)], fill=(0, 212, 255), width=8)
        draw.line([(256, 380), (312, 440)], fill=(0, 212, 255), width=8)
        return img

    def _generate_svg_fallback(self, sizes: list) -> str:
        """Сохраняет SVG-иконку (без PIL)."""
        svg_path = Path(self.output_dir) / "icon.svg"
        svg_path.write_text(DEFAULT_SVG, encoding="utf-8")
        log.info("IconGenerator: PIL недоступен, сохранён SVG → %s", svg_path)
        return f"✅ SVG иконка сохранена: {svg_path} (установи Pillow для растровых)"

    def generate_buildozer_icons(self) -> str:
        """Генерирует иконки в структуре для buildozer."""
        dirs = {
            "drawable-mdpi":  48,
            "drawable-hdpi":  72,
            "drawable-xhdpi": 96,
            "drawable-xxhdpi":144,
            "drawable-xxxhdpi":192,
        }
        os.makedirs("assets/android", exist_ok=True)
        results = []
        for dname, size in dirs.items():
            d = Path("assets/android") / dname
            d.mkdir(parents=True, exist_ok=True)
            try:
                from PIL import Image
                img = self._create_default_pil_icon()
                img.resize((size, size), Image.LANCZOS).save(str(d / "icon.png"))
                results.append(dname)
            except ImportError:
                (d / "icon.svg").write_text(DEFAULT_SVG)
                results.append(f"{dname}(svg)")
        return f"✅ Buildozer иконки: {len(results)} директорий"
