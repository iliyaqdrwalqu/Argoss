from pathlib import Path
from types import SimpleNamespace

from src.core import ArgosCore
from src.connectivity.spatial import ArgosGeolocator, SpatialAwareness
from src.security.encryption import ArgosEncryption, ArgosShield
from src.security.git_guard import GitGuard


def test_argos_shield_kept_as_backward_compatible_alias():
    assert issubclass(ArgosShield, ArgosEncryption)



def test_spatial_awareness_backward_compatible_api(monkeypatch):
    locator = SpatialAwareness(db=object())
    assert isinstance(locator, ArgosGeolocator)

    monkeypatch.setattr(
        locator,
        "get_location",
        lambda ip=None, force=False: {
            "ip": "127.0.0.1",
            "city": "Local",
            "region": "Local",
            "country": "Local",
            "isp": "localhost",
            "lat": 0.0,
            "lon": 0.0,
            "timezone": "UTC",
        },
    )

    report = locator.get_full_report()
    assert "Геолокация" in report
    assert "127.0.0.1" in report



def test_git_guard_check_security_backward_compatible(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("", encoding="utf-8")

    guard = GitGuard(repo_root=str(repo))
    result = guard.check_security()

    assert "GitGuard" in result


def test_core_iot_protocols_help_includes_rs_ttl():
    text = ArgosCore._iot_protocols_help(SimpleNamespace())
    assert "RS TTL / UART TTL" in text
    assert "MAX232" in text
    assert "MAX485" in text


def test_core_driver_report_contains_android_and_gui_checks():
    text = ArgosCore._low_level_drivers_report(SimpleNamespace(otg=None))
    assert "Android USB API (jnius)" in text
    assert "GUI Desktop (customtkinter)" in text


def test_core_driver_report_contains_threads_power_and_video_checks():
    text = ArgosCore._low_level_drivers_report(SimpleNamespace(otg=None))
    assert "Многопоточность CPU" in text
    assert "Питание/мощность" in text
    assert "Видеоядра/GPU" in text


def test_core_voice_services_report_contains_input_output_statuses():
    stub = SimpleNamespace(_tts_engine=object(), voice_on=True)
    text = ArgosCore.voice_services_report(stub)

    assert "Голосовой вывод (TTS)" in text
    assert "Голосовой ввод (микрофон)" in text
    assert "Голосовой ввод (аудиофайлы)" in text
    assert "Текущий голосовой режим: ВКЛ" in text

