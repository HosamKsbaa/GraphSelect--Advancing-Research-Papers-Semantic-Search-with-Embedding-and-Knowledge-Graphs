#!/usr/bin/env bash
# =============================================================================
#  GraphSelect — One-Click Docker Launcher (Linux / macOS)
#  Usage:
#    ./run_graphselect.sh           Start the application
#    ./run_graphselect.sh --stop    Stop and remove containers
# =============================================================================
set -euo pipefail

# ── Constants ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/VERSION" ]]; then
    APP_VERSION=$(cat "$SCRIPT_DIR/VERSION" | tr -d '\r\n ')
else
    APP_VERSION="latest"
fi
IMAGE="ghcr.io/hosamksbaa/graphselect:latest"
COMPOSE_FILE="docker-compose.yml"
HEALTH_URL="http://localhost:8000/api/health"
HEALTH_TIMEOUT=30          # seconds
APP_URL="http://localhost:8000"
ENV_FILE=".env"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Banner ───────────────────────────────────────────────────────────────────
print_banner() {
    echo -e "${CYAN}"
    cat << 'EOF'
   ╔══════════════════════════════════════════════════════════════╗
   ║                                                              ║
   ║    ██████╗ ██████╗  █████╗ ██████╗ ██╗  ██╗                  ║
   ║   ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║  ██║                  ║
   ║   ██║  ███╗██████╔╝███████║██████╔╝███████║                  ║
   ║   ██║   ██║██╔══██╗██╔══██║██╔═══╝ ██╔══██║                  ║
   ║   ╚██████╔╝██║  ██║██║  ██║██║     ██║  ██║                  ║
   ║    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝                  ║
   ║                                                              ║
   ║   ███████╗███████╗██╗     ███████╗ ██████╗████████╗          ║
   ║   ██╔════╝██╔════╝██║     ██╔════╝██╔════╝╚══██╔══╝          ║
   ║   ███████╗█████╗  ██║     █████╗  ██║        ██║             ║
   ║   ╚════██║██╔══╝  ██║     ██╔══╝  ██║        ██║             ║
   ║   ███████║███████╗███████╗███████╗╚██████╗   ██║             ║
   ║   ╚══════╝╚══════╝╚══════╝╚══════╝ ╚═════╝   ╚═╝             ║
   ║                                                              ║
   ║              v${APP_VERSION}  ·  Docker Launcher               ║
   ║                                                              ║
   ╚══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# ── Helpers ──────────────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[  OK]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[FAIL]${NC}  $*"; }

# ── Stop Mode ────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    print_banner
    info "Stopping GraphSelect containers …"
    if [[ -f "$COMPOSE_FILE" ]]; then
        docker compose -f "$COMPOSE_FILE" down --remove-orphans
        success "GraphSelect has been stopped and containers removed."
    else
        warn "No $COMPOSE_FILE found in the current directory."
    fi
    exit 0
fi

# ── Main Flow ────────────────────────────────────────────────────────────────
print_banner

# 1. Check Docker is installed
if ! command -v docker &>/dev/null; then
    error "Docker is not installed or not in PATH."
    echo ""
    echo "  Please install Docker first:"
    echo "    • Linux : https://docs.docker.com/engine/install/"
    echo "    • macOS : https://docs.docker.com/desktop/install/mac-install/"
    echo ""
    exit 1
fi
success "Docker CLI found: $(docker --version)"

# 2. Check Docker daemon is running
if ! docker info &>/dev/null; then
    error "Docker daemon is not running."
    echo ""
    echo "  • On Linux  : sudo systemctl start docker"
    echo "  • On macOS  : Open the Docker Desktop application"
    echo ""
    exit 1
fi
success "Docker daemon is running."

# 3. Gather environment variables
GEMINI_API_KEY=""
OPENALEX_EMAIL=""

# Try to read from existing .env file
if [[ -f "$ENV_FILE" ]]; then
    info "Found existing ${ENV_FILE} — loading values …"
    # shellcheck disable=SC1090
    source "$ENV_FILE" 2>/dev/null || true
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    warn "GEMINI_API_KEY is not set in environment or ${ENV_FILE}."
    warn "You can configure it via the web UI request body."
else
    success "GEMINI_API_KEY is loaded."
fi

if [[ -n "${OPENALEX_EMAIL:-}" ]]; then
    success "OPENALEX_EMAIL is set to: $OPENALEX_EMAIL"
else
    warn "OPENALEX_EMAIL not set — anonymous access will be used."
fi

# 4. Save credentials to .env if set
rm -f "$ENV_FILE"
if [[ -n "${GEMINI_API_KEY:-}" ]]; then
    echo "GEMINI_API_KEY=${GEMINI_API_KEY}" >> "$ENV_FILE"
fi
if [[ -n "${OPENALEX_EMAIL:-}" ]]; then
    echo "OPENALEX_EMAIL=${OPENALEX_EMAIL}" >> "$ENV_FILE"
fi
if [[ -f "$ENV_FILE" ]]; then
    chmod 600 "$ENV_FILE"
    info "Credentials saved to ${ENV_FILE} (chmod 600)."
fi

# 5. Generate docker-compose.yml
info "Generating ${COMPOSE_FILE} …"
cat > "$COMPOSE_FILE" <<COMPEOF
# Auto-generated by run_graphselect.sh — do not edit manually
version: "3.9"

services:
  graphselect:
    image: ${IMAGE}
    container_name: graphselect
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=\${GEMINI_API_KEY}
      - OPENALEX_EMAIL=\${OPENALEX_EMAIL:-}
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-f", "${HEALTH_URL}"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
COMPEOF
success "Generated ${COMPOSE_FILE}."

# 6. Pull latest image & start
info "Pulling latest image …"
docker compose -f "$COMPOSE_FILE" pull
info "Starting GraphSelect in background …"
docker compose -f "$COMPOSE_FILE" up -d

# 7. Poll health endpoint
info "Waiting for server to become healthy (timeout: ${HEALTH_TIMEOUT}s) …"
elapsed=0
while (( elapsed < HEALTH_TIMEOUT )); do
    if curl -sf "$HEALTH_URL" &>/dev/null; then
        success "Server is healthy!"
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    printf "\r  ⏳ %d / %d seconds …" "$elapsed" "$HEALTH_TIMEOUT"
done
echo ""

if (( elapsed >= HEALTH_TIMEOUT )); then
    warn "Health check timed out after ${HEALTH_TIMEOUT}s."
    warn "The container may still be starting — check logs with:"
    echo "    docker compose logs -f graphselect"
    echo ""
fi

# 8. Open browser
info "Opening browser …"
if command -v xdg-open &>/dev/null; then
    xdg-open "$APP_URL" 2>/dev/null &
elif command -v open &>/dev/null; then
    open "$APP_URL"
else
    warn "Could not detect a browser opener. Please visit manually:"
    echo "    $APP_URL"
fi

# 9. Final status
echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  GraphSelect v${APP_VERSION} is running!${NC}"
echo -e "${GREEN}${BOLD}  URL : ${APP_URL}${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Useful commands:"
echo "    • View logs   : docker compose logs -f graphselect"
echo "    • Stop        : ./run_graphselect.sh --stop"
echo "    • Restart     : docker compose restart graphselect"
echo ""
