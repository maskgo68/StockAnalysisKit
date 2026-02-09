from argparse import Namespace

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
