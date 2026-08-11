import { useEffect, useState, type ChangeEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { createPost, runDryRunSchedule } from "../api/posts";
import { PostPreview } from "../components/PostPreview";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { DryRunScheduleResult, PostRecord } from "../types/post";
import { joinLocalDateTime } from "../utils/datetime";

type SubmissionAction = "save" | "dry-run";

export function NewPostPage() {
  const navigate = useNavigate();
  const { status } = useSystemStatus();
  const timezone = status?.timezone ?? "";
  const [caption, setCaption] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [submitting, setSubmitting] = useState<SubmissionAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createdPost, setCreatedPost] = useState<PostRecord | null>(null);
  const [dryRunResult, setDryRunResult] =
    useState<DryRunScheduleResult | null>(null);

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
    setDryRunResult(null);
  }

  async function submit(action: SubmissionAction) {
    setError(null);
    setDryRunResult(null);
    if (!caption.trim() || !image || !date || !time || !timezone) {
      setError("Caption, one image, future date, time, and backend timezone are required.");
      return;
    }
    if (action === "dry-run" && status?.publish_mode !== "dry_run") {
      setError("The backend is not currently in dry-run mode.");
      return;
    }

    setSubmitting(action);
    try {
      const post = await createPost({
        caption,
        image,
        scheduledForLocal: joinLocalDateTime(date, time),
        timezone,
      });
      setCreatedPost(post);
      if (action === "save") {
        navigate(`/posts/${post.id}`);
        return;
      }
      const result = await runDryRunSchedule(post.id);
      setDryRunResult(result);
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
        <h2>Prepare one image post</h2>
        <p>
          Save a durable hosted draft or run the complete scheduling validation as
          an explicit simulation. No Facebook request is available in this phase.
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

      {dryRunResult ? (
        <section className="simulation-result" aria-live="polite">
          <span className="simulation-result__flag">Simulated success</span>
          <div>
            <h3>Dry-run scheduling completed</h3>
            <p>{dryRunResult.message}</p>
            <small>External request made: No · Post remains ready</small>
          </div>
          <Link className="secondary-button secondary-button--link" to={`/posts/${dryRunResult.post_id}`}>
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
            <label htmlFor="image">One image</label>
            <input
              id="image"
              type="file"
              accept=".jpg,.jpeg,.png,image/jpeg,image/png"
              onChange={handleImageChange}
              disabled={submitting !== null}
            />
            <small>JPEG or PNG only. The backend validates content, type, and size.</small>
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
              disabled={submitting !== null || status?.publish_mode !== "dry_run"}
              onClick={() => void submit("dry-run")}
            >
              {submitting === "dry-run" ? "Running simulation…" : "Run Dry-Run Schedule"}
            </button>
          </div>
          <p className="safety-copy">No Facebook request will be sent.</p>
        </section>

        <PostPreview
          caption={caption}
          imageUrl={imagePreviewUrl}
          date={date}
          time={time}
          timezone={timezone}
        />
      </div>
    </div>
  );
}
