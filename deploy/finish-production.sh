#!/usr/bin/env bash
# Финальная настройка VPS: swap, автозапуск, логи Docker, netplan, HTTPS, CORS.
# Запуск на сервере из корня репозитория:
#   chmod +x deploy/finish-production.sh
#   sudo deploy/finish-production.sh
#
# Перед certbot: в Cloudflare для A-записей — «DNS only» (серое облако).

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKEND_DIR="${PROJECT_ROOT}/backend"
DOMAIN="${DOMAIN:-legalai-service.ru}"
WWW_DOMAIN="${WWW_DOMAIN:-www.legalai-service.ru}"
APP_DOMAIN="${APP_DOMAIN:-app.legalai-service.ru}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
NET_IFACE="${NET_IFACE:-enp3s0}"
SWAP_SIZE="${SWAP_SIZE:-2G}"

echo "=== Legal AI: finish production (${DOMAIN}) ==="

# --- 1) Swap ---
if ! swapon --show | grep -q '/swapfile'; then
  echo "[1/8] Creating swap ${SWAP_SIZE}..."
  sudo fallocate -l "${SWAP_SIZE}" /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
else
  echo "[1/8] Swap already active."
fi
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# --- 2) Docker + Nginx autostart ---
echo "[2/8] Enabling docker and nginx..."
sudo systemctl enable docker
sudo systemctl enable nginx

# --- 3) Docker log limits ---
echo "[3/8] Docker log rotation..."
if [ ! -f /etc/docker/daemon.json ]; then
  sudo mkdir -p /etc/docker
  sudo cp "${PROJECT_ROOT}/deploy/docker-daemon.json.example" /etc/docker/daemon.json
  sudo systemctl restart docker
  sleep 3
fi

# --- 4) Netplan (DHCP on main NIC) ---
echo "[4/8] Netplan for ${NET_IFACE}..."
if [ -f "${PROJECT_ROOT}/deploy/netplan-enp3s0.example.yaml" ]; then
  sudo cp "${PROJECT_ROOT}/deploy/netplan-enp3s0.example.yaml" "/etc/netplan/01-legalai.yaml"
  sudo chmod 600 /etc/netplan/01-legalai.yaml
  sudo netplan apply || true
fi
sudo ip link set "${NET_IFACE}" up 2>/dev/null || true
sudo dhclient -v "${NET_IFACE}" 2>/dev/null || true

# --- 5) Backend: API on localhost only, restart stack ---
echo "[5/8] Docker Compose (backend)..."
cd "${BACKEND_DIR}"
docker compose up -d --build
sleep 5
curl -sf http://127.0.0.1:8000/health >/dev/null && echo "  API health OK" || echo "  WARN: API health failed"

# --- 6) Frontend build + nginx ---
echo "[6/8] Frontend build and nginx..."
cd "${PROJECT_ROOT}/frontend"
npm ci
npm run build
sudo mkdir -p /var/www/legalai-service
sudo rsync -a --delete dist/ /var/www/legalai-service/
sudo cp "${PROJECT_ROOT}/deploy/nginx-legalai-service.conf" /etc/nginx/sites-available/legalai-service
sudo ln -sf /etc/nginx/sites-available/legalai-service /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
curl -sf -o /dev/null -w "  /api/health HTTP %{http_code}\n" http://127.0.0.1/api/health

# --- 7) CORS + ACME_EMAIL in .env ---
echo "[7/8] backend/.env (CORS, ACME_EMAIL)..."
ENV_FILE="${BACKEND_DIR}/.env"
touch "${ENV_FILE}"
if ! grep -q '^ACME_EMAIL=' "${ENV_FILE}" 2>/dev/null; then
  if [ -n "${CERTBOT_EMAIL}" ]; then
    echo "ACME_EMAIL=${CERTBOT_EMAIL}" >> "${ENV_FILE}"
  else
    echo "ACME_EMAIL=admin@${DOMAIN}" >> "${ENV_FILE}"
  fi
fi
# Production CORS (http + https until certbot finishes)
CORS_LINE='CORS_ORIGINS=["https://'"${DOMAIN}"'","https://'"${WWW_DOMAIN}"'","http://'"${DOMAIN}"'","http://'"${WWW_DOMAIN}"'"]'
if grep -q '^CORS_ORIGINS=' "${ENV_FILE}"; then
  sed -i "s|^CORS_ORIGINS=.*|${CORS_LINE}|" "${ENV_FILE}"
else
  echo "${CORS_LINE}" >> "${ENV_FILE}"
fi
cd "${BACKEND_DIR}"
docker compose restart api

# --- 8) HTTPS (interactive certbot) ---
echo "[8/8] HTTPS (certbot)..."
if ! command -v certbot >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y certbot python3-certbot-nginx
fi

if [ -z "${CERTBOT_EMAIL}" ]; then
  echo ""
  echo "Запустите certbot вручную (нужен email):"
  echo "  sudo certbot --nginx -d ${DOMAIN} -d ${WWW_DOMAIN} -d ${APP_DOMAIN}"
  echo "  Выберите редирект HTTP -> HTTPS (вариант 2)."
else
  sudo certbot --nginx \
    -d "${DOMAIN}" -d "${WWW_DOMAIN}" -d "${APP_DOMAIN}" \
    --non-interactive --agree-tos -m "${CERTBOT_EMAIL}" \
    --redirect || {
      echo "Certbot failed. Cloudflare: включите DNS only (серое облако) и откройте TCP 80/443."
      exit 1
    }
  # CORS только https после успеха
  CORS_HTTPS='CORS_ORIGINS=["https://'"${DOMAIN}"'","https://'"${WWW_DOMAIN}"'","https://'"${APP_DOMAIN}"'"]'
  sed -i "s|^CORS_ORIGINS=.*|${CORS_HTTPS}|" "${ENV_FILE}"
  docker compose restart api
fi

echo ""
echo "=== Done ==="
echo "  Site:  https://${DOMAIN}"
echo "  API:   https://${DOMAIN}/api/health"
echo "  Check: sudo certbot renew --dry-run"
free -h
