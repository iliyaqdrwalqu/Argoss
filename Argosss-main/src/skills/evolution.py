\
"""Skill re-export: evolution."""
from src.skills.evolution.skill import ArgosEvolution

def register(core):
    return ArgosEvolution(core) if core else None
