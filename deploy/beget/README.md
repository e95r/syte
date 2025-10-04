# Развертывание на хостинге Beget

Этот каталог содержит файлы и инструкции, которые помогут перенести backend на shared-хостинг `cp.beget.com`. Конфигурация
рассчитана на Python-приложение, работающее через Passenger, который есть в тарифах Beget.

## Подготовка окружения

1. **Создайте приложение в панели управления.**
   - В "Python приложения" укажите версию Python 3.12 и директорию `~/syte` (путь можно менять, но примеры ниже используют его).
   - Включите автоматический рестарт и задайте команду запуска `passenger_wsgi.py`.
2. **Подготовьте код локально.**
   ```bash
   git clone https://example.com/syte.git
   cd syte
   cp backend/.env.example backend/.env
   # заполните переменные для боевой среды (PostgreSQL, Redis, SMTP, S3 и т. д.)
   ```
3. **Соберите виртуальное окружение.**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```

## Структура на сервере

На сервер нужно скопировать минимум следующие файлы в директорию приложения (например `~/syte`):

```
backend/
└── ... весь пакет приложения ...
deploy/beget/passenger_wsgi.py  -> passenger_wsgi.py (в корне)
backend/.env                    -> файл с боевыми переменными окружения
```

Убедитесь, что файл `passenger_wsgi.py` лежит рядом с папкой `backend`, иначе Passenger не сможет импортировать модуль.

## Деплой через rsync

Пример автоматизации деплоя из локальной машины:

```bash
export BEGET_USER=your-login
export BEGET_HOST=cp.beget.com
export BEGET_APP_DIR=/home/$BEGET_USER/syte
rsync -avz backend $BEGET_USER@$BEGET_HOST:$BEGET_APP_DIR/
rsync -avz deploy/beget/passenger_wsgi.py $BEGET_USER@$BEGET_HOST:$BEGET_APP_DIR/passenger_wsgi.py
rsync -avz backend/.env $BEGET_USER@$BEGET_HOST:$BEGET_APP_DIR/backend/.env
```

После загрузки выполните на сервере установку зависимостей в виртуальном окружении, созданном из панели или вручную:

```bash
source /home/$BEGET_USER/.local/virtualenvs/syte/bin/activate
pip install -r ~/syte/backend/requirements.txt
```

## Проверка работоспособности

1. В панели управления нажмите «Перезапустить» у приложения. Passenger перечитает `passenger_wsgi.py` и стартует API.
2. В браузере откройте ваш домен и убедитесь, что страница `/ready` возвращает `OK`.
3. Логи приложения можно смотреть в разделе "Логи" → `passenger.log` и `error.log`.

## Полезные советы

- Passenger перезапускает приложение при изменении файлов `*.py`. После деплоя нет нужды вручную останавливать сервис.
- Для обновления зависимостей сначала обновите локально `backend/requirements.lock`, затем на сервере выполните `pip install -r ...`.
- В `.env` обязательно пропишите `PROXY_TRUSTED_HOSTS=*`, если запросы идут через встроенный прокси Beget.
- Если приложение не стартует, проверьте логи Passenger — часто проблема в отсутствии системных пакетов или переменных окружения.
