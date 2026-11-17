# syntax=docker/dockerfile:1

# ---- Estágio 1: compila os assets do frontend (Tailwind, Lucide, Inter) ----
FROM node:22-alpine AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY templates ./templates
COPY apps ./apps
COPY static ./static
RUN npm run build

# ---- Estágio 2: aplicação Django servida pelo Gunicorn ----
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    DATABASE_PATH=/data/db.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=assets /build/static/dist ./static/dist

# Usuário sem privilégios; /data guarda o SQLite (montado como volume).
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /data /media \
    && chown app:app /data /media \
    && chmod +x docker/entrypoint.sh \
    # SECRET_KEY temporária apenas para o collectstatic durante o build.
    && DJANGO_SECRET_KEY="build-only-$(head -c 32 /dev/urandom | base64 | tr -dc A-Za-z0-9)" \
       python manage.py collectstatic --noinput

USER app
EXPOSE 8000
VOLUME ["/data", "/media"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
