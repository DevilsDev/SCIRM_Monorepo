FROM python:3.11-slim

WORKDIR /app

# Install dependencies — in dev mode, requirements.txt is mounted via volume
# For standalone builds, copy requirements first
RUN pip install --no-cache-dir \
    fastapi uvicorn httpx pydantic structlog \
    prometheus-client PyJWT passlib[bcrypt] cryptography

COPY . /app/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
