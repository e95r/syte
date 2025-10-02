# Проверка релиза

## Подготовка окружения

1. `docker compose up --build`
2. `docker compose exec backend alembic upgrade head`
3. Убедитесь, что существует администратор `admin@swimreg.local` (см. README).
4. Очистите тестовые почтовые ящики (MailHog → "Delete all") перед прогоном.

## Стабильные тестовые учетные записи

| Email | Пароль | Назначение |
| --- | --- | --- |
| `admin@swimreg.local` | `admin123` | Настройка соревнований, проверка админки |
| `athlete@example.com` | `athlete123` | Подача индивидуальной заявки |
| `coach@example.com` | `coach123` | Подача командной заявки |

## Чек-лист ручного тестирования

1. **Главная страница**
   - `GET /home` возвращает 200, отображает ближайшие соревнования.
   - Переключатель языка `GET /lang/en` устанавливает cookie и редиректит назад.
2. **Авторизация администратора**
   - Логин через `/auth/login`, после входа появляется доступ к `/admin`.
   - Создать соревнование, убедиться, что оно отображается в списке и на `/home`.
3. **Регистрация участника**
   - Открыть `GET /competitions/{slug}/register`.
   - Отправить индивидуальную заявку (учетная запись `athlete@example.com`).
   - Проверить письма в MailHog: одно участнику, одно администратору.
   - Убедиться, что на `/metrics` появился инкремент для
     `swimreg_registration_submissions_total{registration_type="individual",status="success"}`.
4. **Регистрация команды**
   - Отправить заявку с несколькими участниками от имени `coach@example.com`.
   - Убедиться, что ответ — 303 redirect на страницу соревнования.
   - Проверить, что метрика `swimreg_registration_participants_total` увеличилась
     на количество участников команды.
5. **Админка: подтверждение и синхронизация**
   - Открыть страницу заявки в `/admin` и подтвердить её.
   - Проверить, что быстрые регистрации синхронизировались (см. список участника).
6. **Логи и метрики**
   - `curl -s localhost:8000/metrics | grep swimreg_registration` — значения > 0.
   - `docker compose logs backend | tail` — в логах присутствуют поля
     `status=`, `duration_ms=`, `content_length=`, `ua=` и `request_id=`.

## Негативные сценарии

- Попробовать отправить форму регистрации без участника — должен быть redirect
  с параметром `registered=missing_participant`, статус 303, метрика
  `status="error"` увеличивается.
- Попробовать командную заявку без названия — аналогично `missing_team_name`.

## Завершение

- `docker compose down`
- Сохранить артефакты: `coverage.xml` из CI, `backend-sbom` и отчёт Trivy из
  workflow `Container Release`.
