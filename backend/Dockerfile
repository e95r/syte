FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels

FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        libpq5 \
        libffi8 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY --from=builder /wheels /wheels

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels /root/.cache/pip

COPY . /app

EXPOSE 8000
