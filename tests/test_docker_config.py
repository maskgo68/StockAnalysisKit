from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_compose_healthcheck_uses_app_port_env():
    compose = _read("docker-compose.yml")
    # 避免 compose 健康检查写死端口，需跟 APP_PORT 保持一致。
    assert "os.getenv('APP_PORT'" in compose


def test_compose_has_search_api_envs():
    compose = _read("docker-compose.yml")
    assert "EXA_API_KEY" in compose
    assert "TAVILY_API_KEY" in compose


def test_compose_has_default_ui_language_env():
    compose = _read("docker-compose.yml")
    assert "DEFAULT_UI_LANGUAGE: ${DEFAULT_UI_LANGUAGE:-zh}" in compose


def test_compose_app_port_is_configurable():
    compose = _read("docker-compose.yml")
    assert "APP_PORT: ${APP_PORT:-16888}" in compose


def test_compose_port_mapping_uses_app_port_env():
    compose = _read("docker-compose.yml")
    assert '${STOCKANALYSISKIT_PORT:-16888}:${APP_PORT:-16888}' in compose


def test_compose_has_logging_envs():
    compose = _read("docker-compose.yml")
    assert "LOG_DIR: /app/logs" in compose
    assert "LOG_RETENTION_DAYS: ${LOG_RETENTION_DAYS:-3}" in compose


def test_image_compose_has_default_ui_language_env():
    compose = _read("docker-compose.image.yml")
    assert "DEFAULT_UI_LANGUAGE: ${DEFAULT_UI_LANGUAGE:-zh}" in compose


def test_image_compose_app_port_is_configurable():
    compose = _read("docker-compose.image.yml")
    assert "APP_PORT: ${APP_PORT:-16888}" in compose


def test_image_compose_port_mapping_uses_app_port_env():
    compose = _read("docker-compose.image.yml")
    assert '${STOCKANALYSISKIT_PORT:-16888}:${APP_PORT:-16888}' in compose


def test_image_compose_has_logging_envs():
    compose = _read("docker-compose.image.yml")
    assert "LOG_DIR: /app/logs" in compose
    assert "LOG_RETENTION_DAYS: ${LOG_RETENTION_DAYS:-3}" in compose


def test_dockerfile_has_required_runtime_envs():
    dockerfile = _read("Dockerfile")
    assert "AI_AUTO_CONTINUE_MAX_ROUNDS" in dockerfile
    assert "AI_CLAUDE_MAX_TOKENS" in dockerfile
    assert "EXA_API_KEY" in dockerfile
    assert "TAVILY_API_KEY" in dockerfile
    assert "DEFAULT_UI_LANGUAGE=zh" in dockerfile
    assert "STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS=12" in dockerfile
    assert "LOG_DIR=/app/logs" in dockerfile
    assert "LOG_RETENTION_DAYS=3" in dockerfile


def test_dockerfile_enforces_utf8_runtime_locale():
    dockerfile = _read("Dockerfile")
    assert "LANG=C.UTF-8" in dockerfile
    assert "LC_ALL=C.UTF-8" in dockerfile
    assert "PYTHONIOENCODING=UTF-8" in dockerfile


def test_compose_enforces_utf8_runtime_locale():
    compose = _read("docker-compose.yml")
    assert "LANG: C.UTF-8" in compose
    assert "LC_ALL: C.UTF-8" in compose
    assert "PYTHONIOENCODING: UTF-8" in compose


def test_deploy_compose_uses_prebuilt_dockerhub_image():
    compose = _read("docker-compose.image.yml")
    assert "image: ${STOCKANALYSISKIT_IMAGE:-supergo6/stockanalysiskit:latest}" in compose
    assert "build:" not in compose
