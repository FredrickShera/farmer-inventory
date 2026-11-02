-- 0002_core_tables.sql
-- user_roles, farmers, plots, officer_assignments, inventory_items.
-- Requires 0001. Re-runnable (create ... if not exists).

-- ---------------------------------------------------------------------------
-- user_roles: the TRUSTED source of a user's role (see README "JWT approach").
-- Only the service role / an admin can write it; users cannot edit it, unlike
-- auth.users.raw_user_meta_data which any signed-in user can change.
-- ---------------------------------------------------------------------------
create table if not exists public.user_roles (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  role        public.app_role not null default 'farmer',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  -- lets officer_assignments prove, via a composite FK, that its user is an officer
  constraint user_roles_user_role_key unique (user_id, role)
);

-- ---------------------------------------------------------------------------
-- farmers: one row per registered farmer, linked 1:1 to auth.users.
-- ON DELETE RESTRICT on auth.users: a farmer with history is deactivated
-- (status = 'inactive'), never silently erased by deleting the login.
-- ---------------------------------------------------------------------------
create table if not exists public.farmers (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete restrict,
  full_name    text not null,
  national_id  text not null,
  phone        text not null,
  email        text,
  ward_id      integer not null references public.wards (id) on delete restrict,
  status       public.farmer_status not null default 'active',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint farmers_user_id_key     unique (user_id),
  constraint farmers_national_id_key unique (national_id),
  constraint farmers_phone_key       unique (phone),
  constraint farmers_full_name_check   check (length(btrim(full_name)) between 2 and 120),
  -- Kenyan national IDs are 7-8 digits (older/alien IDs can be 6-9; we accept 6-9)
  constraint farmers_national_id_check check (national_id ~ '^[0-9]{6,9}$'),
  -- 2547XXXXXXXX: country code 254, mobile prefix 7, then 8 digits (12 digits total)
  constraint farmers_phone_check       check (phone ~ '^2547[0-9]{8}$'),
  constraint farmers_email_check       check (email is null or email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$')
);

-- ---------------------------------------------------------------------------
-- plots: a farmer may farm several plots; each plot sits in exactly one ward
-- (county and sub-county are derived through wards -> sub_counties -> counties).
-- Deleting a farmer deletes their plots, but a plot that has inventory cannot be
-- deleted (see inventory_items FK) - retire it with is_active = false instead.
-- ---------------------------------------------------------------------------
create table if not exists public.plots (
  id          uuid primary key default gen_random_uuid(),
  farmer_id   uuid not null references public.farmers (id) on delete cascade,
  name        text not null,
  ward_id     integer not null references public.wards (id) on delete restrict,
  size_acres  numeric(8, 2),
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint plots_farmer_name_key unique (farmer_id, name),
  -- target of the composite FK from inventory_items: proves plot ownership in the DB
  constraint plots_id_farmer_key   unique (id, farmer_id),
  constraint plots_name_check      check (length(btrim(name)) between 1 and 80),
  constraint plots_size_check      check (size_acres is null or size_acres > 0)
);

-- ---------------------------------------------------------------------------
-- officer_assignments: which officer covers which ward (many-to-many).
-- The composite FK guarantees the user really holds the 'officer' role.
-- ---------------------------------------------------------------------------
create table if not exists public.officer_assignments (
  id            uuid primary key default gen_random_uuid(),
  officer_id    uuid not null,
  officer_role  public.app_role not null default 'officer',
  ward_id       integer not null references public.wards (id) on delete restrict,
  created_at    timestamptz not null default now(),
  constraint officer_assignments_officer_ward_key unique (officer_id, ward_id),
  constraint officer_assignments_role_check check (officer_role = 'officer'),
  constraint officer_assignments_officer_fk
    foreign key (officer_id, officer_role)
    references public.user_roles (user_id, role) on delete cascade
);

-- ---------------------------------------------------------------------------
-- inventory_items: what a farmer has ready to sell.
--  * money is integer minor units (KES cents) - never float
--  * composite FK (plot_id, farmer_id) -> plots(id, farmer_id): an item can only
--    point at a plot owned by the same farmer, enforced by the database
--  * soft delete via deleted_at; client_request_id makes POST idempotent
-- ---------------------------------------------------------------------------
create table if not exists public.inventory_items (
  id                    uuid primary key default gen_random_uuid(),
  farmer_id             uuid not null references public.farmers (id) on delete restrict,
  plot_id               uuid not null,
  produce_type_id       integer not null references public.produce_types (id) on delete restrict,
  quantity              numeric(12, 2) not null,
  unit                  public.produce_unit not null,
  grade                 public.quality_grade not null,
  status                public.inventory_status not null default 'available',
  expected_harvest_date date not null,
  asking_price_minor    bigint not null,
  currency              char(3) not null default 'KES',
  client_request_id     uuid,
  sold_at               timestamptz,
  deleted_at            timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint inventory_plot_owner_fk
    foreign key (plot_id, farmer_id)
    references public.plots (id, farmer_id) on delete restrict,
  constraint inventory_quantity_check  check (quantity >= 0),
  constraint inventory_price_check     check (asking_price_minor >= 0),
  constraint inventory_currency_check  check (currency = 'KES'),
  constraint inventory_sold_at_check   check ((status = 'sold') = (sold_at is not null))
);
