-- 0004_functions_and_triggers.sql
-- (a) RLS helper functions, (b) updated_at triggers,
-- (c) "sold items are frozen" trigger, (d) privileged-column guard.

-- ---------------------------------------------------------------------------
-- (a) Helper functions used by the RLS policies in 0005.
-- SECURITY DEFINER so they can read user_roles/farmers/plots/officer_assignments
-- without re-entering RLS (which would recurse). search_path is pinned to '' and
-- every object is schema-qualified, which is the safe way to write definer functions.
-- They only ever answer questions about the CALLER (auth.uid()).
-- ---------------------------------------------------------------------------
create or replace function public.current_app_role()
returns public.app_role
language sql stable security definer
set search_path = ''
as $$
  select ur.role from public.user_roles ur where ur.user_id = auth.uid();
$$;

create or replace function public.is_admin()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select coalesce((select ur.role = 'admin' from public.user_roles ur where ur.user_id = auth.uid()), false);
$$;

create or replace function public.current_farmer_id()
returns uuid
language sql stable security definer
set search_path = ''
as $$
  select f.id from public.farmers f where f.user_id = auth.uid();
$$;

create or replace function public.officer_covers_ward(p_ward_id integer)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.officer_assignments oa
    where oa.officer_id = auth.uid() and oa.ward_id = p_ward_id
  );
$$;

-- An officer sees a farmer whose home ward OR any plot ward is one they cover.
create or replace function public.officer_can_see_farmer(p_farmer_id uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.farmers f
    join public.officer_assignments oa on oa.officer_id = auth.uid()
    where f.id = p_farmer_id
      and (
        f.ward_id = oa.ward_id
        or exists (select 1 from public.plots p where p.farmer_id = f.id and p.ward_id = oa.ward_id)
      )
  );
$$;

-- An officer sees inventory whose PLOT is in a ward they cover.
create or replace function public.officer_can_see_plot(p_plot_id uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.plots p
    join public.officer_assignments oa on oa.ward_id = p.ward_id
    where p.id = p_plot_id and oa.officer_id = auth.uid()
  );
$$;

revoke all on function public.current_app_role()            from public, anon;
revoke all on function public.is_admin()                    from public, anon;
revoke all on function public.current_farmer_id()           from public, anon;
revoke all on function public.officer_covers_ward(integer)  from public, anon;
revoke all on function public.officer_can_see_farmer(uuid)  from public, anon;
revoke all on function public.officer_can_see_plot(uuid)    from public, anon;
grant execute on function public.current_app_role()           to authenticated;
grant execute on function public.is_admin()                   to authenticated;
grant execute on function public.current_farmer_id()          to authenticated;
grant execute on function public.officer_covers_ward(integer) to authenticated;
grant execute on function public.officer_can_see_farmer(uuid) to authenticated;
grant execute on function public.officer_can_see_plot(uuid)   to authenticated;

-- ---------------------------------------------------------------------------
-- (b) updated_at on every mutable table (produce_types already done in 0001)
-- ---------------------------------------------------------------------------
drop trigger if exists user_roles_set_updated_at on public.user_roles;
create trigger user_roles_set_updated_at
  before update on public.user_roles
  for each row execute function public.set_updated_at();

drop trigger if exists farmers_set_updated_at on public.farmers;
create trigger farmers_set_updated_at
  before update on public.farmers
  for each row execute function public.set_updated_at();

drop trigger if exists plots_set_updated_at on public.plots;
create trigger plots_set_updated_at
  before update on public.plots
  for each row execute function public.set_updated_at();

-- Trigger names are prefixed trg1/trg2/trg3 because BEFORE triggers fire in
-- alphabetical order: block first, then stamp sold_at, then bump updated_at.
drop trigger if exists inventory_items_trg3_set_updated_at on public.inventory_items;
create trigger inventory_items_trg3_set_updated_at
  before update on public.inventory_items
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- (c) Sold items are frozen: no UPDATE (including soft delete) and no DELETE,
-- for ANY caller, admins and the service role included. Correcting a sold
-- record is a deliberate DBA action (disable the trigger), never an app path.
-- SQLSTATE 55000 (object_not_in_prerequisite_state) lets the API map it to 409.
-- ---------------------------------------------------------------------------
create or replace function public.inventory_block_sold_changes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.status = 'sold' then
    raise exception 'inventory item % is sold and can no longer be changed', old.id
      using errcode = '55000';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists inventory_items_trg1_block_sold on public.inventory_items;
create trigger inventory_items_trg1_block_sold
  before update or delete on public.inventory_items
  for each row execute function public.inventory_block_sold_changes();

-- Stamp sold_at automatically on the transition to 'sold' so clients cannot forge it.
create or replace function public.inventory_stamp_sold_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'sold' then
    new.sold_at := coalesce(old.sold_at, now());
  else
    new.sold_at := null;
  end if;
  return new;
end;
$$;

drop trigger if exists inventory_items_trg2_stamp_sold_at on public.inventory_items;
create trigger inventory_items_trg2_stamp_sold_at
  before insert or update on public.inventory_items
  for each row execute function public.inventory_stamp_sold_at();

-- ---------------------------------------------------------------------------
-- (d) Privileged-column guard. Row-level policies cannot restrict COLUMNS, so a
-- farmer who may update their own row could otherwise set status/user_id/
-- national_id or move an inventory row to another farmer. Callers that arrive
-- through PostgREST carry a JWT (auth.uid() is not null); the API's own
-- server-side connection does not and is checked in application code.
-- ---------------------------------------------------------------------------
create or replace function public.farmers_guard_privileged_columns()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if auth.uid() is not null and not public.is_admin() then
    if new.status      is distinct from old.status
       or new.user_id     is distinct from old.user_id
       or new.national_id is distinct from old.national_id then
      raise exception 'only an admin may change status, user_id or national_id'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists farmers_guard_privileged on public.farmers;
create trigger farmers_guard_privileged
  before update on public.farmers
  for each row execute function public.farmers_guard_privileged_columns();

create or replace function public.inventory_guard_immutable_columns()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.farmer_id is distinct from old.farmer_id then
    raise exception 'inventory_items.farmer_id is immutable' using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists inventory_items_trg0_guard_immutable on public.inventory_items;
create trigger inventory_items_trg0_guard_immutable
  before update on public.inventory_items
  for each row execute function public.inventory_guard_immutable_columns();
