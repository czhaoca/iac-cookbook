FROM python:3.12-slim

WORKDIR /app

# Install system deps for OCI SDK and SSH
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "nimbus.app:app", "--host", "0.0.0.0", "--port", "8000"]
