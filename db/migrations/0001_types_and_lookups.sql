-- 0001_types_and_lookups.sql
-- Enums, shared trigger function and the lookup tables (locations, produce types).
-- Re-runnable: every statement is idempotent.

-- ---------------------------------------------------------------------------
-- Enums: small CLOSED sets that change with application code, not with data.
-- (Locations and produce types are OPEN sets edited by admins -> lookup tables.)
-- ---------------------------------------------------------------------------
do $$ begin
  create type public.app_role as enum ('farmer', 'officer', 'admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.farmer_status as enum ('active', 'suspended', 'inactive');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.produce_unit as enum ('kg', 'bag', 'crate');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.quality_grade as enum ('A', 'B', 'C');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.inventory_status as enum ('available', 'reserved', 'sold');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Shared updated_at trigger function
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Locations: county -> sub_county -> ward. Three tables so no location text is
-- ever repeated (3NF). `public.locations` (view, 0003) flattens them for reads.
-- ---------------------------------------------------------------------------
create table if not exists public.counties (
  id          integer generated always as identity primary key,
  name        text not null,
  created_at  timestamptz not null default now(),
  constraint counties_name_key unique (name),
  constraint counties_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.sub_counties (
  id          integer generated always as identity primary key,
  county_id   integer not null references public.counties (id) on delete restrict,
  name        text not null,
  created_at  timestamptz not null default now(),
  constraint sub_counties_county_name_key unique (county_id, name),
  constraint sub_counties_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.wards (
  id             integer generated always as identity primary key,
  sub_county_id  integer not null references public.sub_counties (id) on delete restrict,
  name           text not null,
  created_at     timestamptz not null default now(),
  constraint wards_sub_county_name_key unique (sub_county_id, name),
  constraint wards_name_not_blank check (length(btrim(name)) > 0)
);

-- FK columns are not indexed automatically in Postgres; the unique constraints
-- above already cover (county_id, ...) and (sub_county_id, ...) lookups, which
-- is exactly what the dependent dropdowns in the app run.

-- ---------------------------------------------------------------------------
-- Produce types: admin-managed catalogue (open set => lookup table, not enum).
-- ---------------------------------------------------------------------------
create table if not exists public.produce_types (
  id          integer generated always as identity primary key,
  name        text not null,
  category    text not null default 'other',
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint produce_types_name_key unique (name),
  constraint produce_types_name_not_blank check (length(btrim(name)) > 0),
  constraint produce_types_category_check
    check (category in ('cereal', 'legume', 'vegetable', 'fruit', 'tuber', 'cash_crop', 'dairy', 'other'))
);

drop trigger if exists produce_types_set_updated_at on public.produce_types;
create trigger produce_types_set_updated_at
  before update on public.produce_types
  for each row execute function public.set_updated_at();
