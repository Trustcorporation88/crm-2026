FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY *.py ./
COPY .streamlit/ ./.streamlit/
COPY templates/ ./templates/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd -m -u 1000 streamlit \
    && mkdir -p /data /app/Data \
    && chown -R streamlit:streamlit /app /data \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# Stay root so entrypoint can chown the Railway volume, then drop to streamlit.
EXPOSE 8512

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["sh", "-c", "curl -f http://127.0.0.1:${PORT:-8512}/_stcore/health || exit 1"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "if [ \"$CRM_MIGRATION_MODE\" = \"export\" ]; then python migration_export_server.py; else streamlit run crm_app.py --server.port=${PORT:-8512} --server.address=0.0.0.0; fi"]
