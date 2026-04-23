# REST API: Подача в суд и уведомления

## OpenAPI
- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`

## Court Filings API

### `POST /court-filings/submissions`
Подача документов в суд.

Пример запроса:
```json
{
  "case_number": "А40-12345/2026",
  "court_name": "Арбитражный суд г. Москвы",
  "claim_type": "Исковое заявление",
  "documents": [
    {
      "filename": "iskovoe-zayavlenie.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 102400
    }
  ]
}
```

Пример ответа `201`:
```json
{
  "id": 7,
  "case_number": "А40-12345/2026",
  "court_name": "Арбитражный суд г. Москвы",
  "claim_type": "Исковое заявление",
  "status": "submitted",
  "tracking_number": "CF-A1B2C3D4E5F6",
  "comment": null,
  "created_at": "2026-03-23T12:00:00Z",
  "documents": [
    {
      "id": 20,
      "filename": "iskovoe-zayavlenie.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 102400
    }
  ]
}
```

Коды ошибок:
- `400/422` - ошибка валидации документа
- `401` - неавторизованный запрос
- `500` - ошибка сервера

### `GET /court-filings/submissions`
Список подач пользователя с пагинацией (`limit`, `offset`).

### `GET /court-filings/submissions/{filing_id}`
Получить детали подачи.

Коды ошибок:
- `404` - подача не найдена

### `PATCH /court-filings/submissions/{filing_id}/status`
Обновить статус подачи (`submitted`, `received`, `in_review`, `accepted`, `rejected`).

Коды ошибок:
- `404` - подача не найдена
- `422` - некорректный статус

## Notifications API

### `POST /notifications`
Создание уведомления для текущего пользователя.

Пример запроса:
```json
{
  "title": "Изменение статуса подачи в суд",
  "message": "Ваше заявление принято канцелярией суда",
  "notification_type": "court_filing",
  "severity": "high"
}
```

Пример ответа `201`:
```json
{
  "id": 101,
  "title": "Изменение статуса подачи в суд",
  "message": "Ваше заявление принято канцелярией суда",
  "notification_type": "court_filing",
  "severity": "high",
  "is_read": false,
  "read_at": null,
  "created_at": "2026-03-23T12:05:00Z"
}
```

Коды ошибок:
- `401` - неавторизованный запрос
- `422` - ошибка валидации

### `GET /notifications`
Список уведомлений пользователя. Фильтр: `is_read=true|false`.

### `PATCH /notifications/{notification_id}/read`
Отметить уведомление как прочитанное.

Коды ошибок:
- `404` - уведомление не найдено

## Логирование
- Создание подачи в суд: `INFO`
- Обновление статуса подачи: `INFO`
- Ошибки/не найдено: `WARNING`/`ERROR`
- Создание и прочтение уведомлений: `INFO`
