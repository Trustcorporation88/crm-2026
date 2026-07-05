FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY *.py ./
COPY .streamlit/ ./.streamlit/
COPY templates/ ./templates/

RUN useradd -m -u 1000 streamlit && chown -R streamlit:streamlit /app
USER streamlit

ENV CRM_MIGRATION_TOKEN=crm-migrate-20260705-temp

EXPOSE 8512

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["sh", "-c", "curl -f http://127.0.0.1:${PORT:-8512}/health || exit 1"]

CMD ["python", "migration_export_server.py"]
