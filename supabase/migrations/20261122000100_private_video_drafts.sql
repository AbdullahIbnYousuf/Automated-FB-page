-- Preserve all existing image objects and require exactly one type of media.
alter table public.posts
  alter column image_object_path drop not null,
  alter column image_mime_type drop not null,
  add column video_object_path varchar(255) unique,
  add constraint posts_single_media check (
    (image_object_path is not null and image_mime_type is not null and video_object_path is null)
    or (image_object_path is null and image_mime_type is null and video_object_path is not null)
  );

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('post-videos', 'post-videos', false, 20971520, array['video/mp4']);
