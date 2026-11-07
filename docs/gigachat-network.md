# Локальная сеть GigaChat

24.10.2026 в Docker подтверждены повторные `ConnectTimeout` во время TLS.
На том же компьютере соединение из Windows устанавливалось примерно за 0,2 с.
Оба окружения обращались к одному публичному IP. Уменьшение MTU и контрольные
варианты TLS не устранили проблему. Точная причина в сетевом пути Docker Desktop
не установлена; ошибку модели или нехватку токенов эти наблюдения не подтверждают.

Рабочий обход для этого компьютера: фиксированный CONNECT-туннель
`tools/gigachat_tunnel.py`. Он слушает только `127.0.0.1:8766`, разрешает только
`gigachat.devices.sberbank.ru:443` и `www.cbr.ru:443` и передаёт зашифрованные
байты без расшифровки. OAuth и секреты остаются в контейнере. TLS и проверка
имени/сертификата включены. Второй адрес нужен исключительно для официальной
истории ключевой ставки, используемой при расчёте процентов.
Проверка после применения: три `chat/completions` подряд успешно, 0,43 / 0,13 /
0,21 с. Живой опрос с пояснением адреса и пропуском неизвестного поля также прошёл.

Локальный `backend/.env` использует:

```dotenv
GIGACHAT_PROXY_URL=http://host.docker.internal:8766
CBR_PROXY_URL=http://host.docker.internal:8767
```

The local start script starts both fixed tunnel ports.  Port `8766` preserves
the currently running GigaChat route.  Port `8767` is used by the official
Bank of Russia rate-history request, so a changed tunnel policy can take effect
without interrupting an already running model request.  Both ports accept only
the two explicit TLS destinations listed above.

После перезагрузки компьютера из корня проекта запустить:

```powershell
.\tools\start-local-api.ps1
```

Скрипт запускает туннель скрытым процессом, если порт свободен, и применяет
настройки API через Compose. База, Redis и файлы документов сохраняются.
Если Docker Desktop работает без этой сетевой проблемы, переменную
`GIGACHAT_PROXY_URL` можно убрать, затем пересоздать только API.

Клиент переиспользует HTTP-соединение между сообщениями и закрывает его при
остановке API. Таймаут после отправки запроса автоматически не повторяется.
Причины ошибок опроса сохраняются в `provider_failure.kind` без текстов запросов
и токенов: `connection`, `timeout`, `invalid_response`, `limit`, `authorization`.
