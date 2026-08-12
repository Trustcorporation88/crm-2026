#!/bin/sh
set -e

# Prefer explicit CRM_DATA_DIR; otherwise use Railway/Render volume at /data when present.
if [ -z "${CRM_DATA_DIR:-}" ]; then
  if [ -d /data ]; then
    export CRM_DATA_DIR=/data
  else
    export CRM_DATA_DIR=/app/Data
  fi
fi

mkdir -p "$CRM_DATA_DIR"

# A porta é resolvida aqui porque o CMD usa forma exec e não expande ${PORT}.
# O Streamlit lê STREAMLIT_SERVER_PORT do ambiente.
export STREAMLIT_SERVER_PORT="${PORT:-8512}"

# Permissões do diretório de dados.
#
# Antes isto era "chmod -R a+rwX", que deixava o SQLite legível e gravável por
# qualquer processo do contêiner — contornando por completo o controle de
# acesso da aplicação. O dono precisa de rwx no diretório e rw nos arquivos;
# mais do que isso não é requisito de funcionamento, é exposição.
fix_data_perms() {
  chmod 700 "$CRM_DATA_DIR" 2>/dev/null || true
  find "$CRM_DATA_DIR" -type f \( -name '*.sqlite3' -o -name '*.db' -o -name '*-wal' -o -name '*-shm' -o -name '*.journal' \) \
    -exec chmod 600 {} \; 2>/dev/null || true
}

if [ "$(id -u)" = "0" ]; then
  # Volume mounts are often root-owned; chown may be ignored on some volume backends.
  chown -R streamlit:streamlit "$CRM_DATA_DIR" 2>/dev/null || true
  fix_data_perms
  if gosu streamlit sh -c "touch \"$CRM_DATA_DIR/.write_test\" && rm -f \"$CRM_DATA_DIR/.write_test\""; then
    exec gosu streamlit "$@"
  fi
  # Rodar como root é último recurso, não caminho normal: acontece quando o
  # volume montado não aceita escrita pelo usuário sem privilégio. O aviso é
  # ruidoso de propósito, porque é um desvio que merece investigação.
  echo "WARN: $CRM_DATA_DIR não é gravável pelo usuário 'streamlit'." >&2
  echo "WARN: iniciando como root. Corrija a propriedade do volume — rodar" >&2
  echo "WARN: como root em produção anula o isolamento do contêiner." >&2
  exec "$@"
fi

fix_data_perms
exec "$@"
