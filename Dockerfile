FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    postgresql-client \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY web_requirements.txt requirements-prod.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-prod.txt -r web_requirements.txt

# Copy application files
COPY crm_app.py crm_backend.py .streamlit ./

# Create non-root user
RUN useradd -m -u 1000 streamlit && chown -R streamlit:streamlit /app
USER streamlit

# Expose Streamlit port
EXPOSE 8512

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8512/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "crm_app.py", "--server.port=8512", "--server.address=0.0.0.0"]
