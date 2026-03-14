FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Создаём пользователя до копирования файлов
RUN useradd -u 1000 -m appuser

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Создаём venv явно и устанавливаем зависимости в него
RUN uv sync --no-dev --frozen

# Добавляем venv в PATH чтобы uvicorn был доступен напрямую
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source
COPY . .

# Передаём права на всю папку пользователю и делаем скрипт исполняемым
RUN chown -R appuser:appuser /app && chmod +x run.sh

USER appuser

EXPOSE 8000

CMD ["bash", "./run.sh"]
