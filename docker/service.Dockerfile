# Shared image for the API gateway and every agent service.
# Build from the repository root, naming the service directory:
#   docker build -f docker/service.Dockerfile --build-arg SERVICE_PATH=services/coordinator -t scirm/coordinator .
#   docker build -f docker/service.Dockerfile --build-arg SERVICE_PATH=apps/api-gateway -t scirm/api-gateway .
FROM python:3.11-slim

ARG SERVICE_PATH
# Extra pip packages for one service (e.g. the researcher's vector-store client).
ARG EXTRA_PIP=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    SERVICE_PATH=${SERVICE_PATH}

RUN test -n "$SERVICE_PATH" || (echo "SERVICE_PATH build arg is required" >&2 && exit 1) \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin scirm

WORKDIR /app

COPY requirements-service.txt ./
RUN pip install -r requirements-service.txt ${EXTRA_PIP}

COPY libs/ ./libs/
COPY ${SERVICE_PATH}/main.py ./${SERVICE_PATH}/main.py

USER scirm
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)" || exit 1

# exec so uvicorn receives SIGTERM directly and shuts down gracefully.
CMD ["sh", "-c", "exec uvicorn main:app --app-dir \"$SERVICE_PATH\" --host 0.0.0.0 --port 8000"]
