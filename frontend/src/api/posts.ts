import type {
  ScheduleResult,
  PostListResponse,
  PostRecord,
  PostUpdateInput,
} from "../types/post";
import { apiRequest } from "./client";

interface DraftInput {
  caption: string;
  scheduledForLocal: string;
  timezone: string;
}

export type CreatePostInput = DraftInput & (
  { image: File; video?: never } | { video: File; image?: never }
);

export function createPost(input: CreatePostInput): Promise<PostRecord> {
  const form = new FormData();
  form.set("caption", input.caption);
  if (input.video) form.set("video", input.video);
  else form.set("image", input.image);
  form.set("scheduled_for_local", input.scheduledForLocal);
  form.set("timezone", input.timezone);
  return apiRequest<PostRecord>(input.video ? "/api/posts/video" : "/api/posts", {
    method: "POST",
    body: form,
  });
}

export function listPosts(): Promise<PostListResponse> {
  return apiRequest<PostListResponse>("/api/posts");
}

export function getPost(postId: string): Promise<PostRecord> {
  return apiRequest<PostRecord>(`/api/posts/${postId}`);
}

export function updatePost(
  postId: string,
  input: PostUpdateInput,
): Promise<PostRecord> {
  return apiRequest<PostRecord>(`/api/posts/${postId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function schedulePost(postId: string, dryRun = false): Promise<ScheduleResult> {
  return apiRequest<ScheduleResult>(`/api/posts/${postId}/schedule${dryRun ? "?dry_run=true" : ""}`, {
    method: "POST",
  });
}
