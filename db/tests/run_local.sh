#!/usr/bin/env bash
# Applies stub + migrations (twice, to prove they are re-runnable) + seed (twice) + RLS tests
# against a throw-away database. Usage: DB_URL=postgresql://postgres@localhost:5432 ./run_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="${DB_URL:-postgresql://postgres@localhost:5432}"
DB=farmer_test
psql "$BASE/postgres" -v ON_ERROR_STOP=1 -qc "drop database if exists $DB" -c "create database $DB"
URL="$BASE/$DB"
psql "$URL" -v ON_ERROR_STOP=1 -q -f tests/00_supabase_stub.sql
for pass in 1 2; do
  for f in migrations/*.sql; do psql "$URL" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null; done
  echo "migrations pass $pass OK"
done
for pass in 1 2; do psql "$URL" -v ON_ERROR_STOP=1 -q -f seed.sql >/dev/null; echo "seed pass $pass OK"; done
psql "$URL" -v ON_ERROR_STOP=1 -q -o /dev/null -f tests/rls_test.sql
echo "ALL DB TESTS PASSED"
