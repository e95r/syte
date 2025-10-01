# Проверка

## Команды
- `docker compose up --build`
- `docker compose exec backend bash -lc "alembic upgrade head && pytest -q || true"`
- `curl -s localhost:8000/metrics | head -n 20`
- Проверка presigned URL (локальный MinIO, если настроен)

## Контрольные роуты
- `GET /home`
- `GET /lang/{lang}` — установка cookie языка и редирект на исходную страницу
- `GET /metrics`
