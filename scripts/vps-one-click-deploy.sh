#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/maskgo68/StockAnalysisKit.git}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/stockanalysiskit}"
STOCKCOMPARE_PORT="${STOCKCOMPARE_PORT:-16888}"

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
  install_pkg_if_missing git
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

sync_repo() {
  local parent_dir
  parent_dir="$(dirname "$APP_DIR")"
  mkdir -p "$parent_dir"

  if [ -d "$APP_DIR/.git" ]; then
    log "Updating existing repository: $APP_DIR"
    git -C "$APP_DIR" fetch --prune origin
    git -C "$APP_DIR" checkout "$DEPLOY_BRANCH"
    git -C "$APP_DIR" pull --ff-only origin "$DEPLOY_BRANCH"
  elif [ -d "$APP_DIR" ]; then
    echo "APP_DIR exists but is not a git repository: $APP_DIR" >&2
    exit 1
  else
    log "Cloning repository into $APP_DIR"
    git clone --depth 1 --branch "$DEPLOY_BRANCH" "$REPO_URL" "$APP_DIR"
  fi
}

prepare_env_file() {
  local env_file="$APP_DIR/.env"
  local existing_port=""
  mkdir -p "$APP_DIR/data" "$APP_DIR/logs"

  if [ ! -f "$env_file" ]; then
    log "Creating default .env"
    cat > "$env_file" <<EOF
STOCKCOMPARE_PORT=${STOCKCOMPARE_PORT}
NEWS_ITEMS_PER_STOCK=10
EXTERNAL_SEARCH_ITEMS_PER_STOCK=10
# EXA_API_KEY=
# TAVILY_API_KEY=
EOF
  else
    log "Using existing .env"
    existing_port="$(grep -E '^STOCKCOMPARE_PORT=' "$env_file" 2>/dev/null | tail -n1 | cut -d'=' -f2 | tr -d '[:space:]')"
    if [ -n "$existing_port" ]; then
      STOCKCOMPARE_PORT="$existing_port"
    fi
  fi
}

deploy_compose() {
  local compose
  compose="$(compose_cmd)"
  log "Starting containers with: $compose up -d --build"
  # shellcheck disable=SC2086
  $compose -f "$APP_DIR/docker-compose.yml" up -d --build
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

  echo "Health check failed. Inspect logs with: docker compose -f $APP_DIR/docker-compose.yml logs --tail=200" >&2
  exit 1
}

main() {
  ensure_base_dependencies
  install_or_enable_docker
  sync_repo
  prepare_env_file
  deploy_compose
  health_check

  log "Done."
  log "URL: http://<your-vps-ip>:${STOCKCOMPARE_PORT}"
}

main "$@"
