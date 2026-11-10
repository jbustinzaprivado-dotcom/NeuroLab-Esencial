# Una sola imagen con la web compilada, la API y el worker: cabe en un servicio web gratuito.

# 1) Compila la interfaz React.
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2) Python con FastAPI y TensorFlow/Keras.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MALLOC_ARENA_MAX=2 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    NEUROLAB_DATA_DIR=/app/data \
    NEUROLAB_WEB_DIST=/app/web/dist
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY server/ server/
COPY run.py .
COPY --from=web /web/dist web/dist
RUN useradd --create-home neurolab && mkdir -p data && chown -R neurolab /app
USER neurolab
EXPOSE 8000
CMD ["python", "run.py"]
