-- seed.sql — development/demo data. Re-runnable (fixed UUIDs + ON CONFLICT DO NOTHING).
-- Run AFTER all migrations. DEV ONLY: every seeded login uses the password below.
--   password for all seeded users: Passw0rd!2026
-- Seeded logins:
--   admin    admin@coop.example
--   officers officer.nairobi@coop.example (Kitisuru, Kangundo North)
--            officer.rift@coop.example    (Njoro, Lare)
--   farmers  wanjiru@coop.example, kiptoo@coop.example, akinyi@coop.example,
--            mutua@coop.example, halima@coop.example
-- Geography is a small illustrative sample, not the full IEBC list.

-- ---------------------------------------------------------------------------
-- Locations (5 wards in 4 counties)
-- ---------------------------------------------------------------------------
insert into public.counties (name) values ('Nairobi'), ('Kiambu'), ('Nakuru'), ('Machakos')
on conflict (name) do nothing;

insert into public.sub_counties (county_id, name)
select c.id, v.sub_county
from (values
  ('Nairobi',  'Westlands'),
  ('Kiambu',   'Thika Town'),
  ('Nakuru',   'Njoro'),
  ('Machakos', 'Kangundo')
) as v(county, sub_county)
join public.counties c on c.name = v.county
on conflict (county_id, name) do nothing;

insert into public.wards (sub_county_id, name)
select s.id, v.ward
from (values
  ('Westlands',  'Kitisuru'),
  ('Thika Town', 'Township'),
  ('Njoro',      'Njoro'),
  ('Njoro',      'Lare'),
  ('Kangundo',   'Kangundo North')
) as v(sub_county, ward)
join public.sub_counties s on s.name = v.sub_county
on conflict (sub_county_id, name) do nothing;

-- ---------------------------------------------------------------------------
-- Produce catalogue
-- ---------------------------------------------------------------------------
insert into public.produce_types (name, category) values
  ('Maize',        'cereal'),
  ('Beans',        'legume'),
  ('Tomatoes',     'vegetable'),
  ('Kale (Sukuma Wiki)', 'vegetable'),
  ('Potatoes',     'tuber'),
  ('Avocado',      'fruit'),
  ('Mangoes',      'fruit'),
  ('Coffee cherry','cash_crop'),
  ('Milk',         'dairy')
on conflict (name) do nothing;

-- ---------------------------------------------------------------------------
-- Auth users (8: 1 admin, 2 officers, 5 farmers). Inserted directly so the seed
-- works on a fresh Supabase project; they can sign in with the password above.
-- ---------------------------------------------------------------------------
insert into auth.users
  (id, instance_id, aud, role, email, encrypted_password, email_confirmed_at,
   raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
select v.id::uuid, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',
       v.email, extensions.crypt('Passw0rd!2026', extensions.gen_salt('bf')), now(),
       '{"provider":"email","providers":["email"]}'::jsonb,
       jsonb_build_object('full_name', v.full_name), now(), now()
from (values
  ('a0000000-0000-4000-8000-000000000001', 'admin@coop.example',            'Amina Admin'),
  ('b0000000-0000-4000-8000-000000000001', 'officer.nairobi@coop.example',  'Brian Officer'),
  ('b0000000-0000-4000-8000-000000000002', 'officer.rift@coop.example',     'Carol Officer'),
  ('f0000000-0000-4000-8000-000000000001', 'wanjiru@coop.example',          'Wanjiru Mwangi'),
  ('f0000000-0000-4000-8000-000000000002', 'kiptoo@coop.example',           'Peter Kiptoo'),
  ('f0000000-0000-4000-8000-000000000003', 'akinyi@coop.example',           'Grace Akinyi'),
  ('f0000000-0000-4000-8000-000000000004', 'mutua@coop.example',            'Samuel Mutua'),
  ('f0000000-0000-4000-8000-000000000005', 'halima@coop.example',           'Halima Hassan')
) as v(id, email, full_name)
on conflict (id) do nothing;

-- Email identities (needed by GoTrue for password sign-in on some versions).
-- auth.identities.provider_id exists on newer GoTrue; fall back if it does not.
do $$
begin
  begin
    insert into auth.identities (id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
    select gen_random_uuid(), u.id, u.id::text,
           jsonb_build_object('sub', u.id::text, 'email', u.email), 'email', now(), now(), now()
    from auth.users u
    where u.email like '%@coop.example'
      and not exists (select 1 from auth.identities i where i.user_id = u.id and i.provider = 'email');
  exception when undefined_column then
    insert into auth.identities (id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
    select gen_random_uuid(), u.id,
           jsonb_build_object('sub', u.id::text, 'email', u.email), 'email', now(), now(), now()
    from auth.users u
    where u.email like '%@coop.example'
      and not exists (select 1 from auth.identities i where i.user_id = u.id and i.provider = 'email');
  end;
end $$;

-- ---------------------------------------------------------------------------
-- Roles (trusted source) and officer coverage
-- ---------------------------------------------------------------------------
insert into public.user_roles (user_id, role) values
  ('a0000000-0000-4000-8000-000000000001', 'admin'),
  ('b0000000-0000-4000-8000-000000000001', 'officer'),
  ('b0000000-0000-4000-8000-000000000002', 'officer'),
  ('f0000000-0000-4000-8000-000000000001', 'farmer'),
  ('f0000000-0000-4000-8000-000000000002', 'farmer'),
  ('f0000000-0000-4000-8000-000000000003', 'farmer'),
  ('f0000000-0000-4000-8000-000000000004', 'farmer'),
  ('f0000000-0000-4000-8000-000000000005', 'farmer')
on conflict (user_id) do nothing;

insert into public.officer_assignments (officer_id, ward_id)
select v.officer::uuid, w.id
from (values
  ('b0000000-0000-4000-8000-000000000001', 'Kitisuru'),
  ('b0000000-0000-4000-8000-000000000001', 'Kangundo North'),
  ('b0000000-0000-4000-8000-000000000002', 'Njoro'),
  ('b0000000-0000-4000-8000-000000000002', 'Lare')
) as v(officer, ward)
join public.wards w on w.name = v.ward
on conflict (officer_id, ward_id) do nothing;

-- ---------------------------------------------------------------------------
-- Farmers (5)  — phones are obviously fake test numbers
-- ---------------------------------------------------------------------------
insert into public.farmers (id, user_id, full_name, national_id, phone, email, ward_id)
select v.id::uuid, v.user_id::uuid, v.full_name, v.national_id, v.phone, v.email, w.id
from (values
  ('c0000000-0000-4000-8000-000000000001', 'f0000000-0000-4000-8000-000000000001', 'Wanjiru Mwangi', '30000001', '254711000001', 'wanjiru@coop.example', 'Kitisuru'),
  ('c0000000-0000-4000-8000-000000000002', 'f0000000-0000-4000-8000-000000000002', 'Peter Kiptoo',   '30000002', '254711000002', 'kiptoo@coop.example',   'Njoro'),
  ('c0000000-0000-4000-8000-000000000003', 'f0000000-0000-4000-8000-000000000003', 'Grace Akinyi',   '30000003', '254711000003', 'akinyi@coop.example',   'Township'),
  ('c0000000-0000-4000-8000-000000000004', 'f0000000-0000-4000-8000-000000000004', 'Samuel Mutua',   '30000004', '254711000004', 'mutua@coop.example',    'Kangundo North'),
  ('c0000000-0000-4000-8000-000000000005', 'f0000000-0000-4000-8000-000000000005', 'Halima Hassan',  '30000005', '254711000005', 'halima@coop.example',   'Lare')
) as v(id, user_id, full_name, national_id, phone, email, ward)
join public.wards w on w.name = v.ward
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Plots (7; Wanjiru farms in two wards)
-- ---------------------------------------------------------------------------
insert into public.plots (id, farmer_id, name, ward_id, size_acres)
select v.id::uuid, v.farmer::uuid, v.name, w.id, v.acres
from (values
  ('d0000000-0000-4000-8000-000000000001', 'c0000000-0000-4000-8000-000000000001', 'Home plot',   'Kitisuru',       1.50),
  ('d0000000-0000-4000-8000-000000000002', 'c0000000-0000-4000-8000-000000000001', 'Kangundo plot','Kangundo North', 3.00),
  ('d0000000-0000-4000-8000-000000000003', 'c0000000-0000-4000-8000-000000000002', 'Main farm',    'Njoro',          5.25),
  ('d0000000-0000-4000-8000-000000000004', 'c0000000-0000-4000-8000-000000000003', 'Home plot',    'Township',       0.75),
  ('d0000000-0000-4000-8000-000000000005', 'c0000000-0000-4000-8000-000000000004', 'Home plot',    'Kangundo North', 2.00),
  ('d0000000-0000-4000-8000-000000000006', 'c0000000-0000-4000-8000-000000000005', 'Home plot',    'Lare',           4.00),
  ('d0000000-0000-4000-8000-000000000007', 'c0000000-0000-4000-8000-000000000005', 'River plot',   'Lare',           1.25)
) as v(id, farmer, name, ward, acres)
join public.wards w on w.name = v.ward
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Inventory (12 items; prices in KES cents, i.e. 4500 = KES 45.00). One item is sold.
-- ---------------------------------------------------------------------------
insert into public.inventory_items
  (id, farmer_id, plot_id, produce_type_id, quantity, unit, grade, status, expected_harvest_date, asking_price_minor)
select v.id::uuid, v.farmer::uuid, v.plot::uuid, pt.id, v.qty, v.unit::public.produce_unit,
       v.grade::public.quality_grade, v.status::public.inventory_status, v.harvest::date, v.price
from (values
  ('e0000000-0000-4000-8000-000000000001','c0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001','Tomatoes',  120.00,'kg',   'A','available','2026-11-20', 6000),
  ('e0000000-0000-4000-8000-000000000002','c0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001','Kale (Sukuma Wiki)', 40.00,'crate','B','available','2026-11-10', 35000),
  ('e0000000-0000-4000-8000-000000000003','c0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000002','Maize',    25.00,'bag',  'B','reserved', '2026-12-05', 330000),
  ('e0000000-0000-4000-8000-000000000004','c0000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000003','Potatoes', 60.00,'bag',  'A','available','2026-11-25', 250000),
  ('e0000000-0000-4000-8000-000000000005','c0000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000003','Maize',   100.00,'bag',  'C','sold',     '2026-10-01', 280000),
  ('e0000000-0000-4000-8000-000000000006','c0000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000003','Milk',     300.00,'kg',   'A','available','2026-11-03', 5500),
  ('e0000000-0000-4000-8000-000000000007','c0000000-0000-4000-8000-000000000003','d0000000-0000-4000-8000-000000000004','Beans',     15.00,'bag',  'A','available','2026-12-12', 900000),
  ('e0000000-0000-4000-8000-000000000008','c0000000-0000-4000-8000-000000000004','d0000000-0000-4000-8000-000000000005','Mangoes',  200.00,'kg',   'B','available','2026-12-20', 4500),
  ('e0000000-0000-4000-8000-000000000009','c0000000-0000-4000-8000-000000000004','d0000000-0000-4000-8000-000000000005','Avocado',   80.00,'crate','A','reserved', '2026-11-30', 120000),
  ('e0000000-0000-4000-8000-000000000010','c0000000-0000-4000-8000-000000000005','d0000000-0000-4000-8000-000000000006','Coffee cherry', 500.00,'kg','A','available','2026-12-01', 8000),
  ('e0000000-0000-4000-8000-000000000011','c0000000-0000-4000-8000-000000000005','d0000000-0000-4000-8000-000000000007','Tomatoes',  90.00,'crate','C','available','2026-11-15', 90000),
  ('e0000000-0000-4000-8000-000000000012','c0000000-0000-4000-8000-000000000005','d0000000-0000-4000-8000-000000000007','Kale (Sukuma Wiki)', 30.00,'crate','A','available','2026-11-08', 40000)
) as v(id, farmer, plot, produce, qty, unit, grade, status, harvest, price)
join public.produce_types pt on pt.name = v.produce
on conflict (id) do nothing;

-- Supabase Auth expects these token columns to be empty strings, not NULL, for users created via SQL;
-- otherwise password sign-in fails with a 503/500. Guarded so it is skipped on databases without them.
do $$
begin
  update auth.users
  set confirmation_token = coalesce(confirmation_token, ''),
      recovery_token = coalesce(recovery_token, ''),
      email_change_token_new = coalesce(email_change_token_new, ''),
      email_change_token_current = coalesce(email_change_token_current, ''),
      email_change = coalesce(email_change, ''),
      phone_change = coalesce(phone_change, ''),
      phone_change_token = coalesce(phone_change_token, ''),
      reauthentication_token = coalesce(reauthentication_token, '')
  where email like '%@coop.example';
exception when undefined_column then
  null;
end $$;
