-- 0005_rls_policies.sql
-- Row Level Security. Default is DENY: with RLS enabled and no matching policy a
-- row is invisible/unwritable. Roles come from public.user_roles (trusted table),
-- via the SECURITY DEFINER helpers in 0004 - never from user_metadata.
--
--   farmer  -> reads/writes only their own rows
--   officer -> read-only, only farmers/plots/inventory in wards they are assigned
--   admin   -> everything
--
-- The service role (used by the Python API's server-side connection) bypasses RLS
-- by design; the API therefore re-implements the same rules in code (defence in depth).

-- ---------------------------------------------------------------------------
-- Table privileges (least privilege; RLS then narrows rows)
-- ---------------------------------------------------------------------------
revoke all on public.counties, public.sub_counties, public.wards, public.produce_types,
              public.user_roles, public.farmers, public.plots,
              public.officer_assignments, public.inventory_items, public.locations
  from anon, authenticated;

grant select on public.counties, public.sub_counties, public.wards, public.locations to anon, authenticated;
grant select on public.produce_types, public.user_roles, public.officer_assignments to authenticated;
grant insert, update, delete on public.counties, public.sub_counties, public.wards,
                                public.produce_types, public.user_roles,
                                public.officer_assignments to authenticated;  -- admin-only via policies
grant select, insert, update on public.farmers to authenticated;
grant select, insert, update, delete on public.plots to authenticated;
grant select, insert, update, delete on public.inventory_items to authenticated;

alter table public.counties            enable row level security;
alter table public.sub_counties        enable row level security;
alter table public.wards               enable row level security;
alter table public.produce_types       enable row level security;
alter table public.user_roles          enable row level security;
alter table public.farmers             enable row level security;
alter table public.plots               enable row level security;
alter table public.officer_assignments enable row level security;
alter table public.inventory_items     enable row level security;

-- ---------------------------------------------------------------------------
-- Lookups: readable by everyone (the register screen needs them before login),
-- writable by admins only.
-- ---------------------------------------------------------------------------
drop policy if exists counties_read on public.counties;
create policy counties_read on public.counties for select to anon, authenticated using (true);
drop policy if exists counties_admin_write on public.counties;
create policy counties_admin_write on public.counties for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists sub_counties_read on public.sub_counties;
create policy sub_counties_read on public.sub_counties for select to anon, authenticated using (true);
drop policy if exists sub_counties_admin_write on public.sub_counties;
create policy sub_counties_admin_write on public.sub_counties for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists wards_read on public.wards;
create policy wards_read on public.wards for select to anon, authenticated using (true);
drop policy if exists wards_admin_write on public.wards;
create policy wards_admin_write on public.wards for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists produce_types_read on public.produce_types;
create policy produce_types_read on public.produce_types for select to authenticated using (true);
drop policy if exists produce_types_admin_write on public.produce_types;
create policy produce_types_admin_write on public.produce_types for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- user_roles: you can read your own role; only admins can read or change others.
-- There is deliberately NO policy letting a non-admin write here.
-- ---------------------------------------------------------------------------
drop policy if exists user_roles_read_own on public.user_roles;
create policy user_roles_read_own on public.user_roles for select to authenticated
  using (user_id = auth.uid());
drop policy if exists user_roles_admin_all on public.user_roles;
create policy user_roles_admin_all on public.user_roles for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- officer_assignments: an officer sees their own assignments; admins manage all.
-- ---------------------------------------------------------------------------
drop policy if exists officer_assignments_read_own on public.officer_assignments;
create policy officer_assignments_read_own on public.officer_assignments for select to authenticated
  using (officer_id = auth.uid());
drop policy if exists officer_assignments_admin_all on public.officer_assignments;
create policy officer_assignments_admin_all on public.officer_assignments for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- farmers
-- ---------------------------------------------------------------------------
drop policy if exists farmers_read on public.farmers;
create policy farmers_read on public.farmers for select to authenticated
  using (
    user_id = auth.uid()
    or public.is_admin()
    or (public.current_app_role() = 'officer' and public.officer_can_see_farmer(id))
  );

drop policy if exists farmers_insert_self on public.farmers;
create policy farmers_insert_self on public.farmers for insert to authenticated
  with check (user_id = auth.uid() and status = 'active');

drop policy if exists farmers_update_self on public.farmers;
create policy farmers_update_self on public.farmers for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());   -- status/user_id/national_id guarded by trigger

drop policy if exists farmers_admin_all on public.farmers;
create policy farmers_admin_all on public.farmers for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- plots
-- ---------------------------------------------------------------------------
drop policy if exists plots_read on public.plots;
create policy plots_read on public.plots for select to authenticated
  using (
    farmer_id = public.current_farmer_id()
    or public.is_admin()
    or (public.current_app_role() = 'officer' and public.officer_can_see_plot(id))
  );

drop policy if exists plots_write_own on public.plots;
create policy plots_write_own on public.plots for all to authenticated
  using (farmer_id = public.current_farmer_id())
  with check (farmer_id = public.current_farmer_id());

drop policy if exists plots_admin_all on public.plots;
create policy plots_admin_all on public.plots for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- inventory_items. Farmers get no DELETE policy: removal is a soft delete
-- (UPDATE deleted_at). Officers get SELECT only.
-- ---------------------------------------------------------------------------
drop policy if exists inventory_read on public.inventory_items;
create policy inventory_read on public.inventory_items for select to authenticated
  using (
    farmer_id = public.current_farmer_id()
    or public.is_admin()
    or (public.current_app_role() = 'officer' and public.officer_can_see_plot(plot_id))
  );

drop policy if exists inventory_insert_own on public.inventory_items;
create policy inventory_insert_own on public.inventory_items for insert to authenticated
  with check (farmer_id = public.current_farmer_id());

drop policy if exists inventory_update_own on public.inventory_items;
create policy inventory_update_own on public.inventory_items for update to authenticated
  using (farmer_id = public.current_farmer_id())
  with check (farmer_id = public.current_farmer_id());

drop policy if exists inventory_admin_all on public.inventory_items;
create policy inventory_admin_all on public.inventory_items for all to authenticated
  using (public.is_admin()) with check (public.is_admin());
