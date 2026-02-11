from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_vps_deploy_script_is_removed():
    script_path = ROOT / "scripts" / "vps-one-click-deploy.sh"
    assert not script_path.exists()


def test_readme_does_not_reference_removed_vps_script():
    readme = _read("README.md")
    assert "scripts/vps-one-click-deploy.sh" not in readme


def test_readme_does_not_claim_one_click_deploy():
    readme = _read("README.md")
    assert "Docker 一键部署" not in readme
    assert "docker一键运行" not in readme


def test_readme_mentions_manual_docker_run():
    readme = _read("README.md")
    assert "docker run -d --name stockanalysiskit" in readme
    assert "-p 16888:16888" in readme
    assert "-v ./data:/app/data" in readme
