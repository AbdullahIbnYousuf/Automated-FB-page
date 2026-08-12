export type PostStatus =
  | "draft"
  | "ready"
  | "scheduling"
  | "scheduled"
  | "failed"
  | "cancelled";

export type AttemptResult = "in_progress" | "success" | "failed";

export interface SchedulingAttempt {
  id: string;
  mode: "dry_run" | "facebook_schedule";
  result: AttemptResult;
  safe_message: string;
  error_code: string | null;
  external_request_made: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface PostRecord {
  id: string;
  caption: string;
  image_url: string;
  image_mime_type: string;
  original_filename: string;
  status: PostStatus;
  scheduled_for_utc: string;
  scheduled_for_local: string;
  display_timezone: string;
  facebook_object_id: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  last_attempted_at: string | null;
  created_at: string;
  updated_at: string;
  attempts: SchedulingAttempt[];
}

export interface PostListResponse {
  items: PostRecord[];
  total: number;
}

export interface PostUpdateInput {
  caption?: string;
  scheduled_for_local?: string;
  timezone?: string;
}

export interface ScheduleResult {
  mode: "dry_run" | "facebook_schedule";
  simulated: boolean;
  success: boolean;
  post_id: string;
  attempt_id: string;
  post_status: PostStatus;
  external_request_made: boolean;
  facebook_object_id: string | null;
  message: string;
}
