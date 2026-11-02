# Architecture detail

Reference material that sits behind the README. Nothing here is needed to run the project.

## Indexes (each has a one-line reason in `0003_indexes_and_views.sql`)
| Index | Query it serves |
| --- | --- |
| `inventory_items (farmer_id, created_at desc, id) where deleted_at is null` | Farmer's inventory list, newest first |
| `inventory_items (produce_type_id, status) where deleted_at is null` | Filter by produce type and status |
| `inventory_items (plot_id)` | Plot FK and the officer ward join |
| `unique inventory_items (farmer_id, client_request_id)` | Idempotent create |
| `farmers (ward_id, status)` | Farmers by ward and status |
| `plots (farmer_id)`, `plots (ward_id)` | Profile plots, officer scoping |
| `officer_assignments (ward_id)` | Reverse lookup (the `(officer_id, ward_id)` unique key covers the forward one) |

## Row Level Security
| Role | farmers | plots | inventory_items | lookups |
|

## API summary (full OpenAPI at `/docs`)

| Endpoint | Who | Notes |
|

## Tests

| Suite | Command | Count |
| --- | --- | --- |
| API (no external services) | `cd api && python -m pytest` | 63 |
| API against real SQL | `TEST_DATABASE_URL=... python -m pytest tests/test_db_integration.py` | 11 |
| Database (constraints, triggers, RLS) | `db/tests/run_local.sh` | 50 assertions |
| App (unit + component) | `cd app && npm test` | 34 |

Required cases covered: expired token, tampered token, farmer reading another farmer's data, officer outside their ward, negative quantity. The security rules were also mutation-checked: removing the expiry check, the ward scope, the ownership check or the sold check each makes a test fail. The fake repository deliberately does not copy database triggers, so API-layer rules are proven independently of the DB layer.

## Local database proof without Supabase

Needs PostgreSQL 15+. `db/tests/run_local.sh` creates a throw-away database with a small Supabase stub, applies the migrations twice, the seed twice, then runs `db/tests/rls_test.sql`.

## Defence in depth

The API's database connection bypasses RLS (owner credentials), so the same rules are enforced in code and, for anything that talks to Supabase directly, by RLS. The constraints and triggers hold even if both were bypassed (`api/tests/test_db_integration.py`).
