from src.launch_config import normalize_launch_args


def test_normalize_launch_args_keeps_regular_args():
    args = ["--no-gui", "--dashboard"]
    assert normalize_launch_args(args) == args


def test_normalize_launch_args_expands_full_mode():
    assert normalize_launch_args(["--full"]) == ["--full", "--dashboard", "--wake"]


def test_normalize_launch_args_does_not_duplicate_flags():
    assert normalize_launch_args(["--full", "--wake"]) == ["--full", "--wake", "--dashboard"]
