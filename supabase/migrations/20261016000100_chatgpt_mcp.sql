-- Durable idempotency on the existing database. No browser Data API access.
create table public.mcp_operations (
  id varchar(36) primary key default gen_random_uuid()::text,
  operator_id varchar(36) not null,
  tool varchar(64) not null,
  request_key varchar(128) not null,
  fingerprint varchar(64) not null,
  post_id text references public.posts(id) on delete set null,
  response json,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (operator_id, tool, request_key)
);
alter table public.mcp_operations enable row level security;
revoke all on public.mcp_operations from public, anon, authenticated;

-- This project's OAuth client consent is specifically for the scheduler MCP.
-- Supabase supplies client_id and granted scope on BOTH issuance and refresh.
-- Ordinary dashboard sessions have no client_id and are returned unchanged.
create function public.scheduler_mcp_access_token_hook(event jsonb)
returns jsonb
language plpgsql stable
set search_path = ''
as $$
declare
  claims jsonb := event->'claims';
begin
  if coalesce(claims->>'client_id', '') <> ''
     and 'email' = any(string_to_array(coalesce(claims->>'scope', ''), ' ')) then
    claims := jsonb_set(
      claims, '{aud}',
      to_jsonb('https://facebook-page-operations-api.onrender.com/mcp'::text)
    );
  end if;
  return jsonb_build_object('claims', claims);
end;
$$;
revoke all on function public.scheduler_mcp_access_token_hook(jsonb) from public, anon, authenticated;
grant usage on schema public to supabase_auth_admin;
grant execute on function public.scheduler_mcp_access_token_hook(jsonb) to supabase_auth_admin;
