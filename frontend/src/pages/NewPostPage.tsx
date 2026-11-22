import { useEffect, useState, type ChangeEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { createPost, schedulePost } from "../api/posts";
import { PostPreview } from "../components/PostPreview";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { PostRecord, ScheduleResult } from "../types/post";
import { joinLocalDateTime } from "../utils/datetime";

type SubmissionAction = "save" | "schedule";

export function NewPostPage() {
  const navigate = useNavigate();
  const { status } = useSystemStatus();
  const timezone = status?.timezone ?? "";
  const [caption, setCaption] = useState("");
  const [video, setVideo] = useState(false);
  const [image, setImage] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [submitting, setSubmitting] = useState<SubmissionAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createdPost, setCreatedPost] = useState<PostRecord | null>(null);
  const [scheduleResult, setScheduleResult] = useState<ScheduleResult | null>(null);
  const realSchedulingEnabled = !video && status?.publishing_enabled === true;

  useEffect(() => {
    if (!image) {
      setImagePreviewUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(image);
    setImagePreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [image]);

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    setImage(event.target.files?.[0] ?? null);
    setCreatedPost(null);
    setScheduleResult(null);
  }

  async function submit(action: SubmissionAction) {
    setError(null);
    setScheduleResult(null);
    if (!caption.trim() || !image || !date || !time || !timezone) {
      setError("Caption, one media file, future date, time, and backend timezone are required.");
      return;
    }
    if (video && image.size > (status?.max_video_upload_bytes ?? 20 * 1024 * 1024)) {
      setError("The video exceeds the configured upload limit.");
      return;
    }
    if (
      action === "schedule" &&
      !video &&
      status?.publish_mode === "facebook_schedule" &&
      !status.publishing_enabled
    ) {
      setError("Facebook scheduling is disabled by the backend safety gate.");
      return;
    }

    setSubmitting(action);
    try {
      const post = await createPost({
        caption,
        ...(video ? { video: image } : { image }),
        scheduledForLocal: joinLocalDateTime(date, time),
        timezone,
      });
      setCreatedPost(post);
      if (action === "save") {
        navigate(`/posts/${post.id}`);
        return;
      }
      const result = await schedulePost(post.id, video);
      setScheduleResult(result);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The post could not be saved. Check the backend and try again.",
      );
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-panel section-panel--intro compact-intro">
        <span className="eyebrow">Local post workspace</span>
        <h2>Prepare a Page post</h2>
        <p>
          Save one image or video as a private draft. You can test video scheduling
          here with a dry run; nothing will be sent to Facebook.
        </p>
      </section>

      {error ? (
        <section className="notice notice--error" role="alert">
          <div className="notice__icon">!</div>
          <div>
            <h3>Post could not be processed</h3>
            <p>{error}</p>
            {createdPost ? (
              <Link to={`/posts/${createdPost.id}`}>Open the saved draft</Link>
            ) : null}
          </div>
        </section>
      ) : null}

      {scheduleResult ? (
        <section className="simulation-result" aria-live="polite">
          <span className="simulation-result__flag">
            {scheduleResult.simulated ? "Simulated success" : "Facebook scheduled"}
          </span>
          <div>
            <h3>
              {scheduleResult.simulated
                ? "Dry-run scheduling completed"
                : "Scheduled on Facebook"}
            </h3>
            <p>{scheduleResult.message}</p>
            <small>
              {scheduleResult.simulated
                ? "External request made: No · Post remains ready"
                : `Facebook reference: ${scheduleResult.facebook_object_id ?? "Unavailable"}`}
            </small>
          </div>
          <Link className="secondary-button secondary-button--link" to={`/posts/${scheduleResult.post_id}`}>
            View post details
          </Link>
        </section>
      ) : null}

      <div className="composer-layout">
        <section className="composer-panel">
          <div className="field-group">
            <label htmlFor="caption">Caption</label>
            <textarea
              id="caption"
              value={caption}
              onChange={(event) => {
                setCaption(event.target.value);
                setCreatedPost(null);
              }}
              rows={7}
              placeholder="Paste the finished Facebook caption"
              disabled={submitting !== null}
            />
          </div>

          <div className="field-group">
            <label htmlFor="media-type">Post media</label>
            <select id="media-type" value={video ? "video" : "image"} disabled={submitting !== null} onChange={(event) => {
              setVideo(event.target.value === "video");
              setImage(null);
              setCreatedPost(null);
              setScheduleResult(null);
              setError(null);
            }}>
              <option value="image">Image</option>
              <option value="video">Video</option>
            </select>
          </div>

          <div className="field-group">
            <label htmlFor="image">{video ? "One MP4 video" : "One image"}</label>
            <input
              key={video ? "video" : "image"}
              id="image"
              type="file"
              accept={video ? ".mp4,video/mp4" : ".jpg,.jpeg,.png,image/jpeg,image/png"}
              onChange={handleImageChange}
              disabled={submitting !== null}
            />
            <small>{video ? `MP4 (H.264, optional AAC), up to ${(status?.max_video_upload_bytes ?? 20 * 1024 * 1024) / (1024 * 1024)} MiB.` : "JPEG or PNG only. The backend validates content, type, and size."}</small>
          </div>

          <div className="schedule-fields">
            <div className="field-group">
              <label htmlFor="schedule-date">Future date</label>
              <input
                id="schedule-date"
                type="date"
                value={date}
                onChange={(event) => {
                  setDate(event.target.value);
                  setCreatedPost(null);
                }}
                disabled={submitting !== null}
              />
            </div>
            <div className="field-group">
              <label htmlFor="schedule-time">Future time</label>
              <input
                id="schedule-time"
                type="time"
                value={time}
                onChange={(event) => {
                  setTime(event.target.value);
                  setCreatedPost(null);
                }}
                disabled={submitting !== null}
              />
            </div>
          </div>

          <div className="timezone-callout">
            <span>Configured timezone</span>
            <strong>{timezone || "Waiting for backend"}</strong>
            <small>The backend interprets these controls in this timezone.</small>
          </div>

          <div className="composer-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={submitting !== null}
              onClick={() => void submit("save")}
            >
              {submitting === "save" ? "Saving…" : "Save Draft"}
            </button>
            <button
              className="primary-button"
              type="button"
              disabled={
                submitting !== null ||
                !status ||
                (!video && status.publish_mode === "facebook_schedule" && !realSchedulingEnabled)
              }
              onClick={() => void submit("schedule")}
            >
              {submitting === "schedule"
                ? realSchedulingEnabled
                  ? "Scheduling on Facebook…"
                  : "Running simulation…"
                : realSchedulingEnabled
                  ? "Schedule on Facebook"
                  : "Run Dry-Run Schedule"}
            </button>
          </div>
          <p className={`safety-copy${realSchedulingEnabled ? " safety-copy--enabled" : ""}`}>
            {realSchedulingEnabled
              ? "Facebook publishing enabled. This action creates one scheduled Page photo."
              : "Dry run: no Facebook request will be sent."}
          </p>
        </section>

        <PostPreview
          caption={caption}
          imageUrl={imagePreviewUrl}
          video={video}
          date={date}
          time={time}
          timezone={timezone}
        />
      </div>
    </div>
  );
}
