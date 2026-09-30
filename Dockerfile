FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SWAP_DB=/data/swap.db
COPY pyproject.toml README.md ./
COPY swap ./swap
RUN pip install --no-cache-dir .
VOLUME ["/data"]
EXPOSE 8000
# Render, Fly and Railway set $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn swap.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
