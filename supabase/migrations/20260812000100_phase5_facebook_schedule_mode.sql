-- Phase 5 adds one real Facebook scheduling mode to immutable attempt history.

alter table public.scheduling_attempts
  drop constraint if exists scheduling_attempts_mode_check;

alter table public.scheduling_attempts
  add constraint scheduling_attempts_mode_check
  check (mode in ('dry_run', 'facebook_schedule'));
