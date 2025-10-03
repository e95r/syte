# ---------- builder: собираем wheel'ы с ретраями и кэшем ----------
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Инструменты для сборки и dev-заголовки только тут (в runtime не нужны)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      pkg-config \
      python3-dev \
      libpq-dev \
      libcairo2-dev \
      libpango1.0-dev \
      libgdk-pixbuf-2.0-dev \
      libffi-dev \
 && rm -rf /var/lib/apt/lists/*

# Кладём lock-файл с хэшами (и requirements.txt, если используется вместе с lock)
COPY requirements.lock ./requirements.lock
COPY requirements.txt  ./requirements.txt

# Обновляем pip/setuptools/wheel (не ломает --require-hashes)
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel

# Сборка wheel'ов с уважением к хэшам и с использованием кеша BuildKit
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel \
      --require-hashes \
      --progress-bar off \
      --default-timeout=180 \
      -r requirements.lock \
      -w /wheels

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Только runtime-библиотеки
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpq5 \
      libcairo2 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      libffi8 \
      curl \
 && rm -rf /var/lib/apt/lists/*


COPY --from=builder /wheels /wheels
COPY requirements.lock   /app/requirements.lock

RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /app/requirements.lock \
 && rm -rf /wheels /root/.cache/pip


COPY . /app

EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn_conf.py", "app:app"]
