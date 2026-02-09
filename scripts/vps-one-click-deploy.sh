#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/stockanalysiskit}"
STOCKCOMPARE_PORT="${STOCKCOMPARE_PORT:-16888}"
STOCKCOMPARE_IMAGE="${STOCKCOMPARE_IMAGE:-supergo6/stockanalysiskit:latest}"
COMPOSE_URL="${COMPOSE_URL:-https://raw.githubusercontent.com/maskgo68/StockAnalysisKit/main/docker-compose.image.yml}"
COMPOSE_FILE_NAME="docker-compose.image.yml"
COMPOSE_FILE_PATH="${APP_DIR}/${COMPOSE_FILE_NAME}"
ENV_FILE_PATH="${APP_DIR}/.env"

log() {
  printf '[deploy] %s\n' "$1"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root (or use: curl -fsSL ... | sudo bash)" >&2
  exit 1
fi

install_pkg_if_missing() {
  local cmd="$1"
  local apt_name="${2:-$1}"

  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  fi

  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y "$apt_name"
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    dnf install -y "$apt_name"
    return 0
  fi

  if command -v yum >/dev/null 2>&1; then
    yum install -y "$apt_name"
    return 0
  fi

  echo "Cannot install missing dependency: $cmd" >&2
  exit 1
}

ensure_base_dependencies() {
  install_pkg_if_missing curl
}

install_or_enable_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Docker not found, installing via get.docker.com"
    curl -fsSL https://get.docker.com | sh
  else
    log "Docker already installed"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now docker || true
  fi
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi

  echo "Docker Compose is required but not available" >&2
  exit 1
}

download_compose_file() {
  mkdir -p "$APP_DIR"
  log "Downloading deploy compose file"
  curl -fsSL "$COMPOSE_URL" -o "$COMPOSE_FILE_PATH"
}

set_env_value() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  local escaped_value=""

  escaped_value="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"

  if grep -q "^${key}=" "$env_file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$env_file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}

prepare_runtime_env() {
  mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

  if [ ! -f "$ENV_FILE_PATH" ]; then
    log "Creating default .env"
    cat > "$ENV_FILE_PATH" <<EOF
# Runtime image source
STOCKCOMPARE_IMAGE=${STOCKCOMPARE_IMAGE}

# HTTP expose port
STOCKCOMPARE_PORT=${STOCKCOMPARE_PORT}

# Optional external search limits
NEWS_ITEMS_PER_STOCK=10
EXTERNAL_SEARCH_ITEMS_PER_STOCK=10

# Optional keys
# EXA_API_KEY=
# TAVILY_API_KEY=
EOF
  fi

  set_env_value "$ENV_FILE_PATH" "STOCKCOMPARE_IMAGE" "$STOCKCOMPARE_IMAGE"
  set_env_value "$ENV_FILE_PATH" "STOCKCOMPARE_PORT" "$STOCKCOMPARE_PORT"

  if ! grep -q '^NEWS_ITEMS_PER_STOCK=' "$ENV_FILE_PATH"; then
    printf '%s\n' 'NEWS_ITEMS_PER_STOCK=10' >> "$ENV_FILE_PATH"
  fi

  if ! grep -q '^EXTERNAL_SEARCH_ITEMS_PER_STOCK=' "$ENV_FILE_PATH"; then
    printf '%s\n' 'EXTERNAL_SEARCH_ITEMS_PER_STOCK=10' >> "$ENV_FILE_PATH"
  fi
}

deploy_compose() {
  local compose
  compose="$(compose_cmd)"

  log "Pulling image from DockerHub"
  # shellcheck disable=SC2086
  $compose --env-file "$ENV_FILE_PATH" -f "$COMPOSE_FILE_PATH" pull

  log "Starting containers with: $compose up -d --remove-orphans"
  # shellcheck disable=SC2086
  $compose --env-file "$ENV_FILE_PATH" -f "$COMPOSE_FILE_PATH" up -d --remove-orphans
}

health_check() {
  local i
  local url="http://127.0.0.1:${STOCKCOMPARE_PORT}/"

  for i in $(seq 1 30); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "Service is healthy: $url"
      return 0
    fi
    sleep 2
  done

  echo "Health check failed. Inspect logs with: docker compose --env-file $ENV_FILE_PATH -f $COMPOSE_FILE_PATH logs --tail=200" >&2
  exit 1
}

main() {
  ensure_base_dependencies
  install_or_enable_docker
  download_compose_file
  prepare_runtime_env
  deploy_compose
  health_check

  log "Done."
  log "URL: http://<your-vps-ip>:${STOCKCOMPARE_PORT}"
}

main "$@"
