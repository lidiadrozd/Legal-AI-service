# Деплой Legal AI на VPS (legalai-service.ru)

Краткая шпаргалка по серверу **87.242.87.53**, пользователь **student**.

## Быстрый финиш (один скрипт)

На ВМ из корня репозитория:

```bash
cd ~/Legal-AI-service
chmod +x deploy/finish-production.sh
export CERTBOT_EMAIL=ваш@email.com
sudo -E deploy/finish-production.sh
```

Перед certbot в **Cloudflare**: A-записи → **DNS only** (серое облако). В **cloud.ru**: TCP **80**, **443**, **22**.

## Вручную по шагам

### A. Сеть после перезагрузки

```bash
sudo ip link set enp3s0 up
sudo dhclient -v enp3s0
```

Постоянно: `deploy/netplan-enp3s0.example.yaml` → `/etc/netplan/01-legalai.yaml`, `sudo netplan apply`.

### B. Swap 2G

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### C. Автозапуск

```bash
sudo systemctl enable docker nginx
```

### D. Backend

```bash
cd ~/Legal-AI-service/backend
docker compose up -d --build
curl -s http://127.0.0.1:8000/health
```

У **db** только `5432:5432`. У **api** — `127.0.0.1:8000:8000`.

### E. Frontend + Nginx

```bash
cd ~/Legal-AI-service/frontend && npm ci && npm run build
sudo rsync -a --delete dist/ /var/www/legalai-service/
sudo cp ~/Legal-AI-service/deploy/nginx-legalai-service.conf /etc/nginx/sites-available/legalai-service
sudo ln -sf /etc/nginx/sites-available/legalai-service /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### F. HTTPS

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d legalai-service.ru -d www.legalai-service.ru -d app.legalai-service.ru
```

### G. CORS в `backend/.env`

```env
CORS_ORIGINS=["https://legalai-service.ru","https://www.legalai-service.ru","https://app.legalai-service.ru"]
ACME_EMAIL=ваш@email.com
```

```bash
docker compose restart api
```

## Типичные ошибки

| Симптом | Решение |
|--------|---------|
| `Connection timed out` SSH | `dhclient enp3s0`, Security Group TCP 22 |
| `password authentication failed` postgres | `ALTER USER postgres WITH PASSWORD 'postgres';` |
| `80` на контейнере **db** | Убрать `80:8000` у db, только у api или nginx |
| «Не защищено» в браузере | Выпустить certbot (HTTPS) |
| OOM / mysql killed | swap, `systemctl stop mysql` если не нужен |

## ПК выключен

Сайт на ВМ работает. Риски: ребут без netplan, OOM, конец кредитов cloud.ru.
