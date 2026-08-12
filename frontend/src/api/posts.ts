import type {
  ScheduleResult,
  PostListResponse,
  PostRecord,
  PostUpdateInput,
} from "../types/post";
import { apiRequest } from "./client";

export interface CreatePostInput {
  caption: string;
  image: File;
  scheduledForLocal: string;
  timezone: string;
}

export function createPost(input: CreatePostInput): Promise<PostRecord> {
  const form = new FormData();
  form.set("caption", input.caption);
  form.set("image", input.image);
  form.set("scheduled_for_local", input.scheduledForLocal);
  form.set("timezone", input.timezone);
  return apiRequest<PostRecord>("/api/posts", {
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

export function schedulePost(postId: string): Promise<ScheduleResult> {
  return apiRequest<ScheduleResult>(`/api/posts/${postId}/schedule`, {
    method: "POST",
  });
}
