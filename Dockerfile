# ============================================
# Этап 1: Сборка зависимостей
# ============================================
FROM python:3.9-slim as builder

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# Этап 2: Финальный образ
# ============================================
FROM python:3.9-slim

# Метаданные образа
LABEL maintainer="Lincoolns" \
      description="Web dashboard for monitoring Docker containers" \
      version="1.0.0" \
      org.opencontainers.image.title="Docker Dashboard" \
      org.opencontainers.image.description="Beautiful web interface for Docker container management and monitoring" \
      org.opencontainers.image.url="https://github.com/lincoolns/dockerboard"

WORKDIR /app

# Копируем установленные зависимости из builder
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем код приложения
COPY app.py settings.py docker_discovery.py system_stats.py .
COPY templates/ templates/
COPY static/ static/

# Создаем пользователя для безопасности
RUN groupadd -g 1000 dashboard \
    && useradd -m -u 1000 -g dashboard dashboarduser \
    && chown -R dashboarduser:dashboard /app

USER dashboarduser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:5000/ || exit 1

EXPOSE 5000

ENTRYPOINT ["python", "app.py"]
