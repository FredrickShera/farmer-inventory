-- 00_supabase_stub.sql — LOCAL TESTING ONLY. Never run against a real Supabase project.
-- Recreates the tiny slice of Supabase that the migrations depend on, so the
-- schema and RLS policies can be tested on a plain PostgreSQL 15+ server.
do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
do $$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $$;

create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create schema if not exists auth;

create table if not exists auth.users (
  id uuid primary key,
  instance_id uuid, aud text, role text, email text unique,
  encrypted_password text, email_confirmed_at timestamptz,
  raw_app_meta_data jsonb, raw_user_meta_data jsonb,
  created_at timestamptz, updated_at timestamptz
);
create table if not exists auth.identities (
  id uuid primary key, user_id uuid references auth.users (id) on delete cascade,
  provider_id text, identity_data jsonb, provider text,
  last_sign_in_at timestamptz, created_at timestamptz, updated_at timestamptz
);
-- Same behaviour as Supabase: reads the JWT subject PostgREST puts in a GUC.
create or replace function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema public, auth to anon, authenticated, service_role;
grant usage on schema extensions to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
grant all on all tables in schema public to service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
