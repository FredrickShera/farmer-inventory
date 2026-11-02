-- rls_test.sql — proves constraints, triggers and RLS actually DENY. Fails loudly (non-zero exit).
-- Runs on top of seed.sql. Users: see seed.sql for the fixed UUIDs.
\set ON_ERROR_STOP on
\set farmer1  '''f0000000-0000-4000-8000-000000000001'''
\set farmer2  '''f0000000-0000-4000-8000-000000000002'''
\set officer1 '''b0000000-0000-4000-8000-000000000001'''
\set officer2 '''b0000000-0000-4000-8000-000000000002'''
\set admin    '''a0000000-0000-4000-8000-000000000001'''

create or replace function pg_temp.as_user(uid text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', uid, true);
  execute 'set local role authenticated';
end $$;
create or replace function pg_temp.as_service() returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', '', true);
  execute 'reset role';
end $$;
create or replace function pg_temp.expect_eq(label text, actual bigint, expected bigint) returns void language plpgsql as $$
begin
  if actual is distinct from expected then
    raise exception 'FAIL %: expected %, got %', label, expected, actual;
  end if;
  raise notice 'ok   %', label;
end $$;
-- Run a statement; require it to fail with the given SQLSTATE (or any error if null).
create or replace function pg_temp.expect_error(label text, stmt text, state text default null) returns void language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    if state is not null and sqlstate <> state then
      raise exception 'FAIL %: expected SQLSTATE %, got % (%)', label, state, sqlstate, sqlerrm;
    end if;
    raise notice 'ok   % [%]', label, sqlstate;
    return;
  end;
  raise exception 'FAIL %: statement succeeded but should have been denied', label;
end $$;

-- ===== Data-model constraints (as service role / owner) =====
begin;
select pg_temp.as_service();
select pg_temp.expect_eq('seed: >=3 wards',  (select count(*) from wards), 5);
select pg_temp.expect_eq('seed: 5 farmers',  (select count(*) from farmers), 5);
select pg_temp.expect_eq('seed: >=10 items', (select count(*) from inventory_items), 12);
select pg_temp.expect_eq('seed: 2 officers', (select count(*) from user_roles where role='officer'), 2);
select pg_temp.expect_error('negative quantity rejected',
  $q$update inventory_items set quantity = -1 where id = 'e0000000-0000-4000-8000-000000000001'$q$, '23514');
select pg_temp.expect_error('bad phone format rejected',
  $q$update farmers set phone = '0711000001' where id = 'c0000000-0000-4000-8000-000000000001'$q$, '23514');
select pg_temp.expect_error('duplicate national id rejected',
  $q$update farmers set national_id = '30000002' where id = 'c0000000-0000-4000-8000-000000000001'$q$, '23505');
select pg_temp.expect_error('duplicate phone rejected',
  $q$update farmers set phone = '254711000002' where id = 'c0000000-0000-4000-8000-000000000001'$q$, '23505');
select pg_temp.expect_error('grade outside A/B/C rejected',
  $q$update inventory_items set grade = 'D' where id = 'e0000000-0000-4000-8000-000000000001'$q$, '22P02');
select pg_temp.expect_error('unit outside kg/bag/crate rejected',
  $q$update inventory_items set unit = 'tonne' where id = 'e0000000-0000-4000-8000-000000000001'$q$, '22P02');
select pg_temp.expect_error('negative price rejected',
  $q$update inventory_items set asking_price_minor = -5 where id = 'e0000000-0000-4000-8000-000000000001'$q$, '23514');
select pg_temp.expect_error('item cannot point at ANOTHER farmer''s plot (composite FK)',
  $q$update inventory_items set plot_id = 'd0000000-0000-4000-8000-000000000003' where id = 'e0000000-0000-4000-8000-000000000001'$q$, '23503');
select pg_temp.expect_error('plot with inventory cannot be deleted (RESTRICT)',
  $q$delete from plots where id = 'd0000000-0000-4000-8000-000000000001'$q$, '23503');
select pg_temp.expect_error('ward with farmers cannot be deleted (RESTRICT)',
  $q$delete from wards where name = 'Njoro'$q$, '23503');
select pg_temp.expect_error('officer assignment requires officer role (composite FK)',
  $q$insert into officer_assignments (officer_id, ward_id) select 'f0000000-0000-4000-8000-000000000001', id from wards limit 1$q$, '23503');
-- sold item is frozen, for everyone including the service role
select pg_temp.expect_error('sold item cannot be updated',
  $q$update inventory_items set quantity = 1 where id = 'e0000000-0000-4000-8000-000000000005'$q$, '55000');
select pg_temp.expect_error('sold item cannot be soft-deleted',
  $q$update inventory_items set deleted_at = now() where id = 'e0000000-0000-4000-8000-000000000005'$q$, '55000');
select pg_temp.expect_error('sold item cannot be deleted',
  $q$delete from inventory_items where id = 'e0000000-0000-4000-8000-000000000005'$q$, '55000');
-- sold_at stamped by trigger; updated_at bumped by trigger
update inventory_items set status = 'sold' where id = 'e0000000-0000-4000-8000-000000000004';
select pg_temp.expect_eq('sold_at stamped on sale', (select count(*) from inventory_items where id='e0000000-0000-4000-8000-000000000004' and sold_at is not null), 1);
update farmers set full_name = 'Wanjiru W. Mwangi' where id = 'c0000000-0000-4000-8000-000000000001';
select pg_temp.expect_eq('updated_at trigger bumps timestamp',
  (select count(*) from farmers where id='c0000000-0000-4000-8000-000000000001' and updated_at >= now()), 1);
rollback;

-- ===== RLS: farmer sees only their own rows =====
begin;
select pg_temp.as_user(:farmer1);
select pg_temp.expect_eq('farmer1 sees only own farmer row', (select count(*) from farmers), 1);
select pg_temp.expect_eq('farmer1 sees only own inventory', (select count(*) from inventory_items), 3);
select pg_temp.expect_eq('farmer1 sees only own plots', (select count(*) from plots), 2);
select pg_temp.expect_eq('farmer1 cannot read other farmer by id',
  (select count(*) from farmers where id = 'c0000000-0000-4000-8000-000000000002'), 0);
select pg_temp.expect_eq('farmer1 cannot read user_roles of others', (select count(*) from user_roles), 1);
-- writes against another farmer's rows silently affect 0 rows (RLS filters them out)
with u as (update inventory_items set quantity = 1 where farmer_id = 'c0000000-0000-4000-8000-000000000002' returning 1)
  select pg_temp.expect_eq('farmer1 cannot update farmer2 inventory', (select count(*) from u), 0);
with u as (update farmers set full_name = 'Hacked' where id = 'c0000000-0000-4000-8000-000000000002' returning 1)
  select pg_temp.expect_eq('farmer1 cannot update farmer2 profile', (select count(*) from u), 0);
select pg_temp.expect_error('farmer1 cannot insert inventory for farmer2 (WITH CHECK)',
  $q$insert into inventory_items (farmer_id, plot_id, produce_type_id, quantity, unit, grade, expected_harvest_date, asking_price_minor)
     values ('c0000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000003',1,5,'kg','A','2026-12-01',100)$q$, '42501');
with u as (update user_roles set role = 'admin' where user_id = 'f0000000-0000-4000-8000-000000000001' returning 1)
  select pg_temp.expect_eq('farmer cannot promote self to admin (no write policy => 0 rows)', (select count(*) from u), 0);
select pg_temp.expect_eq('role change really did not happen',
  (select count(*) from public.user_roles where role='admin' and user_id='f0000000-0000-4000-8000-000000000001'), 0);
select pg_temp.expect_error('farmer cannot change own status (guard trigger)',
  $q$update farmers set status = 'suspended' where id = 'c0000000-0000-4000-8000-000000000001'$q$, '42501');
select pg_temp.expect_error('farmer cannot change own national_id (guard trigger)',
  $q$update farmers set national_id = '99999999' where id = 'c0000000-0000-4000-8000-000000000001'$q$, '42501');
with d as (delete from inventory_items where farmer_id = 'c0000000-0000-4000-8000-000000000001' returning 1)
  select pg_temp.expect_eq('farmer has no hard-delete on inventory (0 rows)', (select count(*) from d), 0);
rollback;

begin;
select pg_temp.as_user(:farmer1);
update farmers set full_name = 'Wanjiru W. Mwangi' where id = 'c0000000-0000-4000-8000-000000000001';
select pg_temp.expect_eq('farmer1 CAN update own name', (select count(*) from farmers where full_name = 'Wanjiru W. Mwangi'), 1);
update inventory_items set quantity = 99 where id = 'e0000000-0000-4000-8000-000000000001';
select pg_temp.expect_eq('farmer1 CAN update own inventory', (select count(*) from inventory_items where quantity = 99), 1);
rollback;

-- ===== RLS: officer is read-only and ward-scoped =====
begin;
select pg_temp.as_user(:officer1);   -- covers Kitisuru + Kangundo North
select pg_temp.expect_eq('officer1 sees farmers in own wards (Wanjiru, Samuel)', (select count(*) from farmers), 2);
select pg_temp.expect_eq('officer1 sees inventory in own wards', (select count(*) from inventory_items), 5);
select pg_temp.expect_eq('officer1 cannot see Rift Valley farmer',
  (select count(*) from farmers where id = 'c0000000-0000-4000-8000-000000000002'), 0);
with u as (update inventory_items set quantity = 1 returning 1)
  select pg_temp.expect_eq('officer1 cannot update inventory', (select count(*) from u), 0);
select pg_temp.expect_error('officer1 cannot insert inventory',
  $q$insert into inventory_items (farmer_id, plot_id, produce_type_id, quantity, unit, grade, expected_harvest_date, asking_price_minor)
     values ('c0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001',1,5,'kg','A','2026-12-01',100)$q$, '42501');
select pg_temp.expect_error('officer1 cannot assign self more wards',
  $q$insert into officer_assignments (officer_id, ward_id) select 'b0000000-0000-4000-8000-000000000001', id from wards where name='Njoro'$q$, '42501');
rollback;

begin;
select pg_temp.as_user(:officer2);   -- covers Njoro + Lare
select pg_temp.expect_eq('officer2 sees farmers in own wards (Peter, Halima)', (select count(*) from farmers), 2);
select pg_temp.expect_eq('officer2 sees only Rift inventory', (select count(*) from inventory_items), 6);
rollback;

-- ===== RLS: admin sees and writes everything =====
begin;
select pg_temp.as_user(:admin);
select pg_temp.expect_eq('admin sees all farmers', (select count(*) from farmers), 5);
select pg_temp.expect_eq('admin sees all inventory', (select count(*) from inventory_items), 12);
update farmers set status = 'suspended' where id = 'c0000000-0000-4000-8000-000000000001';
select pg_temp.expect_eq('admin CAN change status', (select count(*) from farmers where status = 'suspended'), 1);
select pg_temp.expect_error('even admin cannot edit a sold item',
  $q$update inventory_items set quantity = 2 where id = 'e0000000-0000-4000-8000-000000000005'$q$, '55000');
rollback;

-- ===== anon =====
begin;
select pg_temp.as_service();
set local role anon;
select pg_temp.expect_eq('anon can read locations', (select count(*) from locations), 5);
select pg_temp.expect_error('anon cannot read farmers', $q$select * from farmers$q$, '42501');
select pg_temp.expect_error('anon cannot read inventory', $q$select * from inventory_items$q$, '42501');
rollback;

\echo 'rls_test.sql: all assertions passed'
