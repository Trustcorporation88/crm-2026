FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# requirements-docker.txt apenas referencia requirements.txt ("-r"), então os
# dois precisam estar presentes. Ficam numa camada isolada do código para que
# alterar um .py não invalide o cache da instalação de dependências.
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

# Forma exec, sem "sh -c" envolvendo.
#
# Duas razões. A primeira é sinal: com "sh -c", o PID 1 do contêiner era o
# shell, que não repassa SIGTERM ao filho — o Streamlit nunca recebia o pedido
# de parada e acabava morto por SIGKILL ao fim do timeout, sem encerramento
# gracioso. Agora o processo do Streamlit é o próprio PID 1.
#
# A segunda é que o CMD antigo ramificava em CRM_MIGRATION_MODE e trocava o
# CRM inteiro pelo servidor de exportação da base. Bastava uma variável de
# ambiente para transformar o serviço num endpoint de download do banco. Quem
# precisar exportar deve invocar o script explicitamente:
#   docker compose run --rm app python migration_export_server.py
#
# A porta é resolvida pelo entrypoint via STREAMLIT_SERVER_PORT, já que a
# forma exec não expande ${PORT}.
CMD ["streamlit", "run", "crm_app.py", "--server.address=0.0.0.0"]
