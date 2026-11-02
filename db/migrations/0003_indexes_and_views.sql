-- 0003_indexes_and_views.sql
-- One index per query the app/API really runs. Each has a one-line reason.

-- Inventory by farmer, newest first (farmer's list screen; GET /inventory as farmer). Partial: soft-deleted rows are never listed.
create index if not exists inventory_items_farmer_created_idx
  on public.inventory_items (farmer_id, created_at desc, id) where deleted_at is null;

-- Filtered inventory by produce type and status (GET /inventory?produce_type_id=&status= for officers/admins).
create index if not exists inventory_items_produce_status_idx
  on public.inventory_items (produce_type_id, status) where deleted_at is null;

-- Inventory by plot: backs the plot FK and the officer ward join (inventory -> plot -> ward).
create index if not exists inventory_items_plot_idx
  on public.inventory_items (plot_id);

-- Idempotent create: one row per (farmer, client_request_id), makes double-taps / retries safe.
create unique index if not exists inventory_items_client_request_key
  on public.inventory_items (farmer_id, client_request_id) where client_request_id is not null;

-- Farmers by ward and status (GET /farmers?ward_id=&status=; officer scoping).
create index if not exists farmers_ward_status_idx
  on public.farmers (ward_id, status);

-- Plots by farmer (GET /farmers/me includes plots; backs the plots -> farmers FK).
create index if not exists plots_farmer_idx
  on public.plots (farmer_id);

-- Plots by ward (officer scope: which farmers/inventory sit in my ward).
create index if not exists plots_ward_idx
  on public.plots (ward_id);

-- Officer coverage by ward (reverse lookup; (officer_id, ward_id) is already covered by its unique key).
create index if not exists officer_assignments_ward_idx
  on public.officer_assignments (ward_id);

-- Wards by sub-county for the dependent dropdown is covered by wards_sub_county_name_key; counties/sub_counties likewise.

-- ---------------------------------------------------------------------------
-- Flattened read model for the "locations lookup" (county > sub-county > ward).
-- security_invoker: the view runs with the CALLER's privileges, so RLS on the
-- underlying tables still applies.
-- ---------------------------------------------------------------------------
create or replace view public.locations
  with (security_invoker = true) as
select
  w.id   as ward_id,
  w.name as ward,
  s.id   as sub_county_id,
  s.name as sub_county,
  c.id   as county_id,
  c.name as county
from public.wards w
join public.sub_counties s on s.id = w.sub_county_id
join public.counties c on c.id = s.county_id;
