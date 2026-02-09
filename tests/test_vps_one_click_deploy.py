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
    assert "pull" in content
    assert "up -d --remove-orphans" in content
    assert "--build" not in content


def test_vps_deploy_script_uses_prebuilt_image_deploy_flow():
    content = _read("scripts/vps-one-click-deploy.sh")
    assert "STOCKCOMPARE_IMAGE" in content
    assert "supergo6/stockanalysiskit:latest" in content
    assert "docker-compose.image.yml" in content
    assert "git clone" not in content


def test_readme_does_not_show_optional_vps_script_section():
    readme = _read("README.md")
    assert "VPS 一键部署脚本（可选）" not in readme
    assert "scripts/vps-one-click-deploy.sh" not in readme


def test_readme_mentions_minimal_one_line_docker_run():
    readme = _read("README.md")
    assert "docker run -d --name stockanalysiskit" in readme
    assert "-p 16888:16888" in readme
    assert "-v ./data:/app/data" in readme
