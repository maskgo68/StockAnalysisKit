from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_vps_deploy_script_exists_and_uses_safe_shell_settings():
    script_path = ROOT / "scripts" / "vps-one-click-deploy.sh"
    assert script_path.exists()
    content = _read("scripts/vps-one-click-deploy.sh")
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content


def test_vps_deploy_script_installs_or_checks_docker_then_runs_compose_up():
    content = _read("scripts/vps-one-click-deploy.sh")
    assert "get.docker.com" in content
    assert "docker compose" in content
    assert "up -d --build" in content


def test_vps_deploy_script_clones_or_updates_repo():
    content = _read("scripts/vps-one-click-deploy.sh")
    assert "git clone" in content
    assert "pull --ff-only" in content
    assert "REPO_URL" in content


def test_readme_mentions_one_command_vps_deploy():
    readme = _read("README.md")
    assert "VPS 一键部署" in readme
    assert "curl -fsSL" in readme
    assert "scripts/vps-one-click-deploy.sh" in readme
