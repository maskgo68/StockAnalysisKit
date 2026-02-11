from argparse import Namespace
import logging
import time

import app


def test_default_app_port_is_16888():
    assert app.APP_PORT == 16888


def test_parse_args_supports_serve_flag():
    args = app._parse_args(["--serve"])
    assert args.serve is True


def test_start_server_in_new_console_on_windows(monkeypatch, capsys):
    monkeypatch.setattr(app.os, "name", "nt", raising=False)
    monkeypatch.setattr(app, "_pid_listening_on_port", lambda _port: None)
    monkeypatch.setattr(app, "_is_process_running", lambda _pid: False)
    monkeypatch.setattr(app.subprocess, "CREATE_NEW_CONSOLE", 0x00000010, raising=False)

    popen_calls = {}

    class DummyProc:
        pid = 4321

    def fake_popen(cmd, **kwargs):
        popen_calls["cmd"] = cmd
        popen_calls["kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(app.subprocess, "Popen", fake_popen)

    app._start_server_in_new_console()

    assert popen_calls["cmd"][-1] == "--serve"
    assert popen_calls["kwargs"]["creationflags"] == app.subprocess.CREATE_NEW_CONSOLE
    output = capsys.readouterr().out
    assert "PID=" in output
    assert "python app.py --status" in output
    assert "python app.py --stop" in output


def test_handle_cli_runs_server_directly_for_serve_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda: calls.append("run"))
    monkeypatch.setattr(app, "_start_server_in_new_console", lambda: calls.append("start"))
    monkeypatch.setattr(app.os, "name", "nt", raising=False)

    app._handle_cli(Namespace(status=False, stop=False, serve=True))

    assert calls == ["run"]


def test_handle_cli_uses_new_console_on_windows_default(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "_run_server", lambda: calls.append("run"))
    monkeypatch.setattr(app, "_start_server_in_new_console", lambda: calls.append("start"))
    monkeypatch.setattr(app.os, "name", "nt", raising=False)

    app._handle_cli(Namespace(status=False, stop=False, serve=False))

    assert calls == ["start"]


def test_cleanup_old_logs_removes_files_older_than_three_days(tmp_path):
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    old_log.write_text("old", encoding="utf-8")
    new_log.write_text("new", encoding="utf-8")

    now_ts = time.time()
    five_days_ago = now_ts - (5 * 24 * 60 * 60)
    one_day_ago = now_ts - (1 * 24 * 60 * 60)
    old_log.touch()
    new_log.touch()
    # Set deterministic mtimes for retention checks.
    import os

    os.utime(old_log, (five_days_ago, five_days_ago))
    os.utime(new_log, (one_day_ago, one_day_ago))

    removed = app._cleanup_old_logs(tmp_path, retention_days=3, now_ts=now_ts)

    assert removed == 1
    assert not old_log.exists()
    assert new_log.exists()


def test_configure_logging_writes_to_file_and_auto_cleans(monkeypatch, tmp_path):
    old_log = tmp_path / "expired.log"
    old_log.write_text("expired", encoding="utf-8")
    now_ts = time.time()
    old_ts = now_ts - (4 * 24 * 60 * 60)
    import os

    os.utime(old_log, (old_ts, old_ts))

    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_RETENTION_DAYS", "3")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    app._configure_logging()

    logging.getLogger("tests.lifecycle").info("log smoke test")
    for handler in logging.getLogger().handlers:
        if hasattr(handler, "flush"):
            handler.flush()

    assert (tmp_path / "app.log").exists()
    assert not old_log.exists()
