"""Skill package: Сетевой Призрак"""
__version__ = "1.2.0"

__all__ = ["NetGhost"]


def __getattr__(name: str):
    if name == "NetGhost":
        from src.skills.net_scanner.skill import NetGhost as _NetGhost

        return _NetGhost
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
