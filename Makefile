.PHONY: api-install api-test api-run db-test app-install app-test app-start
api-install: ; cd api && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
api-test:    ; cd api && .venv/bin/python -m pytest
api-run:     ; cd api && .venv/bin/uvicorn app.main:create_app --factory --reload
db-test:     ; db/tests/run_local.sh   # needs a local PostgreSQL 15+ (see README)
app-install: ; cd app && npm install
app-test:    ; cd app && npm test
app-start:   ; cd app && npx expo start
