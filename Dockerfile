# ---------- painel React ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- backend Django + workers ----------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright DJANGO_DEBUG=false

# Node (Lighthouse/axe-core) e bibliotecas do WeasyPrint.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates gnupg libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt && python -m playwright install --with-deps chromium
COPY backend/package.json backend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend/dist
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput

RUN useradd -m auditor && mkdir -p /app/backend/media && chown -R auditor /app/backend/media /ms-playwright
USER auditor
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
