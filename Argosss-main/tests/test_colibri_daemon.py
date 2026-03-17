import builtins

import pytest

import colibri_daemon


def test_parse_args_supports_daemon_mode_and_pid_file():
    args = colibri_daemon._parse_args(["--daemon", "--pid-file", "/tmp/colibri.pid"])
    assert args.daemon is True
    assert args.pid_file == "/tmp/colibri.pid"
    assert args.work_dir == "data/colibri"


def test_run_daemon_background_exits_when_python_daemon_missing(monkeypatch, capsys):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "daemon":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    args = colibri_daemon._parse_args(["--daemon"])

    with pytest.raises(SystemExit) as exc:
        colibri_daemon.run_daemon_background(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "python-daemon не установлен" in out
