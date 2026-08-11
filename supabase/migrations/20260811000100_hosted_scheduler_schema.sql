-- Hosted scheduler schema: PostgreSQL is authoritative; Storage remains private.

create table if not exists public.posts (
  id text primary key default gen_random_uuid()::text,
  caption text not null check (length(btrim(caption)) > 0),
  image_object_path varchar(255) not null unique,
  image_mime_type varchar(32) not null
    check (image_mime_type in ('image/jpeg', 'image/png')),
  original_filename varchar(255) not null,
  status varchar(20) not null default 'draft'
    check (status in ('draft', 'ready', 'scheduling', 'scheduled', 'failed', 'cancelled')),
  scheduled_for_utc timestamptz not null,
  display_timezone varchar(64) not null default 'Asia/Dhaka',
  facebook_object_id varchar(255),
  last_error_code varchar(64),
  last_error_message text,
  last_attempted_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists ix_posts_status on public.posts (status);
create index if not exists ix_posts_created_at on public.posts (created_at desc);

create table if not exists public.scheduling_attempts (
  id text primary key default gen_random_uuid()::text,
  post_id text not null references public.posts(id) on delete cascade,
  mode varchar(20) not null check (mode in ('dry_run')),
  result varchar(20) not null
    check (result in ('in_progress', 'success', 'failed')),
  safe_message text not null,
  error_code varchar(64),
  external_request_made boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz
);

create index if not exists ix_scheduling_attempts_post_id
  on public.scheduling_attempts (post_id);
create index if not exists ix_scheduling_attempts_created_at
  on public.scheduling_attempts (created_at desc);

alter table public.posts enable row level security;
alter table public.scheduling_attempts enable row level security;
revoke all on table public.posts from anon, authenticated;
revoke all on table public.scheduling_attempts from anon, authenticated;

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'post-images',
  'post-images',
  false,
  5242880,
  array['image/jpeg', 'image/png']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
