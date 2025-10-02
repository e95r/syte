# syte

## Development environment notes

- The PostgreSQL container runs on the `postgres:16-alpine` image to match the
  persisted database volume. Update your local images accordingly before
  starting the stack.
- Run `docker compose down -v` **only** when you intentionally want to remove
  the database volume and rebuild it from scratch. This command deletes all
  persisted data.

## Полный сценарий запуска окружения

1. Скопируйте переменные окружения (можно создать файл `backend/.env` на основе
   примера ниже). Значения по умолчанию подходят для локальной разработки.

   ```env
   SECRET_KEY=dev-secret
   DATABASE_URL=postgresql+psycopg2://swimuser:s3curePg2025!@postgres:5432/swimdb
   MEDIA_DIR=/app/storage/media
   DOCS_DIR=/app/storage/docs
   RESULTS_DIR=/app/storage/results
   STATIC_DIR=/app/storage/static
   ```

2. Запустите инфраструктуру: `docker compose up --build`.
3. Примените миграции: `docker compose exec backend alembic upgrade head`.
4. Создайте базового администратора (одна и та же команда безопасно выполняется
   повторно):

   ```bash
   docker compose exec backend bash -lc 'python - <<"PY"
   from db import SessionLocal
   from models import User
   from security import get_password_hash

   session = SessionLocal()
   try:
       user = session.query(User).filter_by(email="admin@swimreg.local").one_or_none()
       if user is None:
           user = User(
               email="admin@swimreg.local",
               username="admin",
               full_name="Администратор",
               hashed_password=get_password_hash("admin123"),
               is_admin=True,
           )
           session.add(user)
           session.commit()
           print("Администратор создан: admin@swimreg.local / admin123")
       else:
           print("Администратор уже существует")
   finally:
       session.close()
   PY'
   ```

5. Создайте тестовые учетные записи, используемые в ручном чек-листе:

   ```bash
   docker compose exec backend bash -lc 'python - <<"PY"
   from db import SessionLocal
   from models import User
   from security import get_password_hash

   users = [
       {"email": "athlete@example.com", "username": "athlete", "full_name": "Иван Пловец"},
       {"email": "coach@example.com", "username": "coach", "full_name": "Мария Тренер"},
   ]

   session = SessionLocal()
   try:
       for payload in users:
           user = session.query(User).filter_by(email=payload["email"]).one_or_none()
           if user is None:
               user = User(
                   **payload,
                   hashed_password=get_password_hash("athlete123" if payload["username"] == "athlete" else "coach123"),
               )
               session.add(user)
       session.commit()
       print("Тестовые учетные записи готовы: athlete@example.com / athlete123, coach@example.com / coach123")
   finally:
       session.close()
   PY'
   ```

6. (Необязательно) Заполните демонстрационные данные через интерфейс админки.
7. Убедитесь, что сервисы подняты: откройте `http://localhost:8000/home` и
   `http://localhost:8025` (MailHog для писем).
8. Проверьте метрики и логи:
   - `curl -s localhost:8000/metrics | head` — стандартные и бизнес-метрики
     (например, `swimreg_registration_submissions_total`).
   - `docker compose logs -f backend` — логи запросов с полями method, path,
     статус, длительность, размер ответа и user-agent.
9. Запустите автотесты (используется отдельная SQLite-БД и стабильные учетные
   записи): `docker compose exec backend pytest -q`.

## Частые проблемы и решения

| Симптом | Решение |
| --- | --- |
| `psycopg2.OperationalError: could not connect to server` при выполнении миграций | Убедитесь, что контейнер `postgres` прогрелся (`docker compose logs postgres`). Повторите `alembic upgrade head` через пару секунд. |
| Ошибка `permission denied` при записи результатов/медиа | Проверьте, что каталоги из `.env` существуют и доступны контейнеру (`docker compose exec backend ls /app/storage`). |
| Письма не приходят | Запустите MailHog (`docker compose up mailhog`) и убедитесь, что `SMTP_HOST=mailhog`. |
| Нет данных на `/metrics` | Проверьте, что приложение стартовало без ошибок и что запросы выполнялись (бизнес-метрики появляются после успешных действий). |

## Наблюдаемость и метрики

- `/metrics` экспортирует стандартные метрики FastAPI и бизнес-показатели:
  - `swimreg_registration_submissions_total` — количество заявок с признаком
    успех/ошибка и типом регистрации (индивидуальная/командная).
  - `swimreg_registration_duration_seconds` — гистограмма времени обработки
    заявок.
  - `swimreg_registration_participants_total` — число участников в успешных
    заявках.
- Логи запросов (`swimreg.requests`) содержат host, method, path, статус,
  длительность в мс, размер ответа, user-agent и request-id — этого достаточно
  для настройки алертов в Loki/ELK.

## Безопасность сессий

- Access-токены действуют 15 минут и выдаются вместе с refresh-токеном в
  HttpOnly-cookie.
- Refresh-токены хранятся в базе в виде HMAC-хэшей, привязаны к IP и
  User-Agent и автоматически ротируются при обновлении access-токена.
- `/auth/logout` отзывает все активные refresh-сессии пользователя.
- Настраиваемые параметры находятся в `settings.py`:
  `REFRESH_TOKEN_EXPIRE_DAYS`, `REFRESH_TOKEN_MAX_SESSIONS`,
  `REFRESH_TOKEN_SECRET`.

## Тестирование

- Юнит-тесты используют фабрики и отдельные SQLite-БД, поэтому безопасно
  запускаются параллельно (`pytest -n auto`).
- Для сбора покрытия используется `pytest --cov`, отчет публикуется в CI как
  артефакт (`coverage.xml`).
