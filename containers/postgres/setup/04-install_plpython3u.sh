#!/usr/bin/env bash
# https://www.postgresql.org/docs/current/plpython.html

set -e

PSQL_CMD="psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --port ${PSQL_PORT}"

# PostgreSQL databases

for dbname in "${PSQL_DB}" "${PSQL_DBF}"; do
  echo "Creating extension and function in database: ${dbname}"
  echo "CREATE EXTENSION IF NOT EXISTS plpython3u\gexec" | ${PSQL_CMD} -d ${dbname}
  echo "Creating extract_SE function in database: ${dbname}"
  ${PSQL_CMD} -d ${dbname} -f /docker-entrypoint-initdb.d/05-extract_SE.sql
done
