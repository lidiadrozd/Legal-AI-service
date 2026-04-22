# Legal-AI-service

Демо-конфиг **уже заполнен** (IP `87.242.87.53`, суперадмин, CORS `*`, секреты для теста).

## Быстрый старт

### Сервер (Docker)

```bash
cd backend
docker compose up -d --build
```

- API: **http://87.242.87.53:8000** (откройте порт **8000** в фаерволе) или `http://localhost:8000` на самой машине.
- Из корня репозитория: `docker compose up -d --build` (нужен Compose 2.20+).

### Фронтенд (ПК)

```bash
cd frontend
npm install
npm run dev
```

`VITE_API_BASE_URL` уже задан в **`.env.development`** / **`.env.production`** / **`.env.local`** на ваш VPS.

**Только локальный бэкенд** (без VPS): в `frontend/.env.development` замените на `VITE_API_BASE_URL=http://127.0.0.1:8000` или удалите строку (будет прокси `/api` → `127.0.0.1:8000`).

### Вход суперадмина (после первого старта API)

- Email: `admin@demo.local`
- Пароль: `DemoLegal2026!`

### HTTPS без покупки домена

В `.env` задано `TRAEFIK_API_DOMAIN=87-242-87-53.nip.io` (nip.io резолвится в ваш IP). Профиль:

```bash
cd backend
docker compose --profile https up -d --build
```

Профили **`traefik`** и **`https`** не включайте вместе (порт 80).

### Полезное

- Docker переопределяет `DATABASE_URL` / Redis на хосты `db` / `redis`.
- Уведомления: Redis + WebSocket `/api/ws/notifications`; при недоступном Redis API не падает.
- По умолчанию мониторинг использует открытый источник КонсультантПлюс (`https://www.consultant.ru/law/review/fed/updprof/`) и преобразует его в изменения законов.
- При необходимости можно переопределить источники через `LAW_CHANGE_SOURCES` (через запятую). Поддерживается JSON-формат с полем `changes`.
- Документы: поддержаны API `POST /documents/upload`, `GET /documents/templates`, `POST /documents/generate` (TXT/DOCX/PDF), `GET /documents`, `GET /documents/{id}/download`, `DELETE /documents/{id}`.
