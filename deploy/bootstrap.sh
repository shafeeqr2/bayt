#!/usr/bin/env bash
# Prepare a fresh Ubuntu 24.04 server for Bayt. Run once, as root:
#
#   curl -fsSL https://raw.githubusercontent.com/kkamilahmed/bayt/main/deploy/bootstrap.sh \
#     | sudo bash -s -- "ssh-ed25519 AAAA... you@laptop"
#
# The argument is the public SSH key for the `deploy` user (the key text or a file
# path). Without it, root's authorized_keys are copied. Running the script again is
# safe: every step checks its own result first. See docs/deploy.md.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/kkamilahmed/bayt.git}"
APP_DIR=/opt/bayt
DEPLOY_USER=deploy
PUBKEY="${1:-}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run this script as root (sudo)."
export DEBIAN_FRONTEND=noninteractive

info "Base packages"
apt-get update -q
apt-get install -y -q ca-certificates curl git gnupg ufw

if ! command -v docker >/dev/null 2>&1; then
  info "Docker Engine and the Compose plugin from Docker's apt repository"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

if [[ ! -f /etc/docker/daemon.json ]]; then
  info "Docker log rotation (10 MB x 3 per container)"
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
  systemctl restart docker
fi

if [[ ! -f /swapfile ]]; then
  info "2 GB swap file (the frontend build needs more memory than a 4 GB server has spare)"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

info "User '$DEPLOY_USER' with Docker access"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
AUTH="$HOME_DIR/.ssh/authorized_keys"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$HOME_DIR/.ssh"
touch "$AUTH"
if [[ -n "$PUBKEY" ]]; then
  if [[ -f "$PUBKEY" ]]; then PUBKEY="$(cat "$PUBKEY")"; fi
  if ! grep -qxF "$PUBKEY" "$AUTH"; then echo "$PUBKEY" >> "$AUTH"; fi
elif [[ -s /root/.ssh/authorized_keys ]]; then
  while IFS= read -r line; do
    if [[ -n "$line" ]] && ! grep -qxF "$line" "$AUTH"; then echo "$line" >> "$AUTH"; fi
  done < /root/.ssh/authorized_keys
else
  fail "No SSH key for '$DEPLOY_USER'. Pass a public key as the first argument, or add one to /root/.ssh/authorized_keys first."
fi
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH"
chmod 600 "$AUTH"

info "Firewall: allow SSH, HTTP and HTTPS only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 443/udp >/dev/null   # HTTP/3
ufw --force enable >/dev/null
ufw status | sed 's/^/    /'

if [[ ! -d "$APP_DIR/.git" ]]; then
  info "Cloning $REPO_URL into $APP_DIR"
  install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
  sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
  info "Writing $APP_DIR/.env from the template"
  cat > "$APP_DIR/.env" <<'ENV'
# Production settings for Bayt. Docker Compose reads this file. It is not in git.

# Makes a plain `docker compose` in /opt/bayt use the production overlay.
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml

# Model API key (Nebius Token Factory keys start with v1.). Empty turns the
# model features off; the deterministic parts still work. See README.md.
LLM_API_KEY=
ZONING_MODEL=
PHOTO_MODEL=
PROFILE_MODEL=
EMBED_MODEL=

# Used only by the development override (host ports). Kept so every variable
# in docker-compose.yml resolves without a warning.
POSTGRES_PORT=5433
BACKEND_PORT=8000
FRONTEND_PORT=3000
ENV
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

cat <<EOT

Done. Next steps:

  1. Put the model key in $APP_DIR/.env (LLM_API_KEY=...).
  2. Point the DNS A record for bayt.andalsolutions.com at this server's IP.
     Caddy needs it to get the certificate.
  3. First deploy, as the deploy user:
       sudo -iu $DEPLOY_USER $APP_DIR/deploy/deploy.sh
  4. In the GitHub repo, add the Actions secrets DEPLOY_HOST (this IP),
     DEPLOY_USER ($DEPLOY_USER) and DEPLOY_SSH_KEY (the private key that matches
     the public key in $AUTH). After that every push to main deploys.
  5. Optional: copy your local database up so the model-written profiles are
     not recomputed. See docs/deploy.md.
EOT
