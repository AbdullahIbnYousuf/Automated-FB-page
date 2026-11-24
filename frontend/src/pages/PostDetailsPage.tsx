import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { getPost, schedulePost, scheduleVideoOnFacebook, updatePost } from "../api/posts";
import { AuthenticatedImage } from "../components/AuthenticatedImage";
import { AuthenticatedVideo } from "../components/AuthenticatedVideo";
import { AttemptStatusBadge, PostStatusBadge } from "../components/PostStatusBadge";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { PostRecord, ScheduleResult } from "../types/post";
import {
  formPartsFromLocalIso,
  formatUtcDateTime,
  formatZonedDateTime,
  joinLocalDateTime,
} from "../utils/datetime";

interface VideoReview {
  post: PostRecord;
  pageId: string;
}

export function PostDetailsPage() {
  const { postId } = useParams();
  const { status: systemStatus, refresh: refreshSystem } = useSystemStatus();
  const [post, setPost] = useState<PostRecord | null>(null);
  const [caption, setCaption] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [loading, setLoading] = useState(Boolean(postId));
  const [saving, setSaving] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const schedulingLock = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scheduleResult, setScheduleResult] = useState<ScheduleResult | null>(null);
  const [videoReview, setVideoReview] = useState<VideoReview | null>(null);
  const realSchedulingEnabled = !post?.video_url && systemStatus?.publishing_enabled === true;
  const videoPageId = systemStatus?.video_publishing_enabled === true
    ? systemStatus.video_scheduling_page_id : null;

  const applyPost = useCallback((record: PostRecord) => {
    const parts = formPartsFromLocalIso(record.scheduled_for_local);
    setPost(record);
    setCaption(record.caption);
    setDate(parts.date);
    setTime(parts.time);
    setVideoReview(null);
  }, []);

  const load = useCallback(async () => {
    if (!postId) return;
    setLoading(true);
    setError(null);
    try {
      applyPost(await getPost(postId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Post could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [applyPost, postId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveEdits() {
    if (!post) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updatePost(post.id, {
        caption,
        scheduled_for_local: joinLocalDateTime(date, time),
        timezone: post.display_timezone,
      });
      applyPost(updated);
      setNotice("Changes saved. The post is a draft until scheduling validation runs again.");
      setScheduleResult(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Changes could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function runSchedule(review?: VideoReview) {
    if (!post || schedulingLock.current) return;
    if (review && (review.post.id !== post.id || review.post.updated_at !== post.updated_at || review.pageId !== videoPageId)) return;
    schedulingLock.current = true;
    setScheduling(true);
    setScheduleResult(null);
    setError(null);
    setNotice(null);
    try {
      const result = review
        ? await scheduleVideoOnFacebook(review.post, review.pageId)
        : await schedulePost(post.id, Boolean(post.video_url));
      setScheduleResult(result);
      await load();
    } catch (caught) {
      await load();
      if (review && caught instanceof ApiError && caught.code === "VIDEO_REVIEW_STALE") {
        void refreshSystem();
      }
      setError(caught instanceof ApiError ? caught.message : "The scheduling response was interrupted. Check this post and Facebook before submitting again.");
    } finally {
      setVideoReview(null);
      schedulingLock.current = false;
      setScheduling(false);
    }
  }

  if (!postId) {
    return (
      <section className="empty-state">
        <div className="empty-state__mark">—</div>
        <h2>No post selected</h2>
        <p>Choose a persisted record from the Posts screen.</p>
        <Link className="secondary-button secondary-button--link" to="/posts">Browse posts</Link>
      </section>
    );
  }

  if (loading) {
    return <section className="empty-state"><div className="empty-state__mark">…</div><h2>Loading post</h2></section>;
  }

  if (!post) {
    return (
      <section className="empty-state">
        <div className="empty-state__mark">!</div>
        <h2>Post unavailable</h2><p>{error}</p>
        <Link className="secondary-button secondary-button--link" to="/posts">Return to posts</Link>
      </section>
    );
  }

  const unknownOutcome = post.last_error_code === "FACEBOOK_OUTCOME_UNKNOWN";
  const editBlocked =
    ["scheduling", "scheduled", "cancelled"].includes(post.status) || unknownOutcome;
  const realModeBlocked =
    !post.video_url && systemStatus?.publish_mode === "facebook_schedule" && !realSchedulingEnabled;
  const savedTime = formPartsFromLocalIso(post.scheduled_for_local);
  const hasUnsavedEdits = caption !== post.caption || date !== savedTime.date || time !== savedTime.time;
  const editorLocked = editBlocked || saving || scheduling || videoReview !== null;

  return (
    <div className="page-stack">
      <section className="detail-heading">
        <div>
          <span className="eyebrow">Persistent post record</span>
          <h2>Post details</h2>
          <p className="record-id">Internal ID: {post.id}</p>
        </div>
        <PostStatusBadge status={post.status} />
      </section>

      {error ? <section className="notice notice--error" role="alert"><div className="notice__icon">!</div><div><h3>Action failed</h3><p>{error}</p></div></section> : null}
      {notice ? <section className="notice"><div className="notice__icon">✓</div><div><h3>Saved</h3><p>{notice}</p></div></section> : null}
      {scheduleResult ? (
        <section className="simulation-result" aria-live="polite">
          <span className="simulation-result__flag">
            {scheduleResult.simulated ? "Simulated success" : "Facebook scheduled"}
          </span>
          <div>
            <h3>{scheduleResult.simulated ? "Dry run completed" : "Scheduled on Facebook"}</h3>
            <p>{scheduleResult.message}</p>
            <small>
              {scheduleResult.simulated
                ? "External request made: No · Facebook ID created: No"
                : `Facebook reference: ${scheduleResult.facebook_object_id ?? "Unavailable"}`}
            </small>
          </div>
        </section>
      ) : null}

      <div className="detail-layout">
        <section className="detail-card detail-card--media">
          {post.video_url ? <AuthenticatedVideo path={post.video_url} /> : post.image_url ? <AuthenticatedImage path={post.image_url} alt="Uploaded post" /> : null}
          <div><span>{post.video_url ? "Stored video" : "Stored image"}</span><strong>{post.original_filename}</strong><small>{post.video_url ? "video/mp4" : post.image_mime_type}</small></div>
        </section>

        <section className="composer-panel detail-editor">
          <div className="field-group">
            <label htmlFor="detail-caption">Caption</label>
            <textarea id="detail-caption" rows={7} value={caption} onChange={(event) => setCaption(event.target.value)} disabled={editorLocked} />
          </div>
          <div className="schedule-fields">
            <div className="field-group"><label htmlFor="detail-date">Date</label><input id="detail-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} disabled={editorLocked} /></div>
            <div className="field-group"><label htmlFor="detail-time">Time</label><input id="detail-time" type="time" value={time} onChange={(event) => setTime(event.target.value)} disabled={editorLocked} /></div>
          </div>
          <div className="timezone-callout"><span>Configured timezone</span><strong>{post.display_timezone}</strong><small>Browser timezone is not used for interpretation.</small></div>
          <div className="composer-actions">
            <button className="secondary-button" type="button" disabled={editorLocked} onClick={() => void saveEdits()}>{saving ? "Saving…" : "Save Changes"}</button>
            <button className={post.video_url && videoPageId ? "secondary-button" : "primary-button"} type="button" disabled={editorLocked || !systemStatus || realModeBlocked} onClick={() => void runSchedule()}>
              {scheduling && !videoReview
                ? realSchedulingEnabled
                  ? "Scheduling on Facebook…"
                  : "Running simulation…"
                : realSchedulingEnabled
                  ? "Schedule on Facebook"
                  : "Run Dry-Run Schedule"}
            </button>
            {post.video_url && videoPageId && !videoReview ? (
              <button className="primary-button" type="button" disabled={editorLocked || hasUnsavedEdits} onClick={() => setVideoReview({ post, pageId: videoPageId })}>
                Review Facebook Video Schedule
              </button>
            ) : null}
          </div>
          <p className={`safety-copy${realSchedulingEnabled ? " safety-copy--enabled" : ""}`}>
            {unknownOutcome
              ? "Outcome unknown: check Meta before any further action."
              : realSchedulingEnabled
                ? "Facebook publishing enabled. This action creates one scheduled Page photo."
                : "Dry run: no Facebook request will be sent."}
          </p>
          {post.video_url && !editBlocked && !videoReview ? (
            <p className="safety-copy">
              {videoPageId ? (hasUnsavedEdits ? "Save your caption or time changes before reviewing a live schedule." : "Live video scheduling requires a separate review and confirmation.") : "Live video scheduling is disabled."}
            </p>
          ) : null}
          {videoReview ? (
            <fieldset className="video-scheduling-review" disabled={scheduling}>
              <legend>Confirm Facebook video schedule</legend>
              <p><strong>Video:</strong> {videoReview.post.original_filename} (shown in the preview)</p>
              <p><strong>Facebook Page ID:</strong> {videoReview.pageId}</p>
              <p><strong>Time:</strong> {formatZonedDateTime(videoReview.post.scheduled_for_utc, videoReview.post.display_timezone, true)} ({videoReview.post.display_timezone})</p>
              <div><strong>Caption:</strong><p className="video-scheduling-review__caption">{videoReview.post.caption}</p></div>
              <p className="safety-copy">This sends one real scheduling request to Facebook.</p>
              <div className="composer-actions">
                <button className="secondary-button" type="button" onClick={() => setVideoReview(null)}>Cancel</button>
                <button className="primary-button" type="button" disabled={videoPageId !== videoReview.pageId} onClick={() => void runSchedule(videoReview)}>
                  {scheduling ? "Scheduling video…" : "Schedule Video on Facebook"}
                </button>
              </div>
            </fieldset>
          ) : null}
        </section>
      </div>

      <section className="metadata-grid">
        <div><span>Local schedule</span><strong>{formatZonedDateTime(post.scheduled_for_utc, post.display_timezone)}</strong><small>{post.display_timezone}</small></div>
        <div><span>UTC schedule</span><strong>{formatUtcDateTime(post.scheduled_for_utc)}</strong><small>Stored in PostgreSQL as aware UTC</small></div>
        <div><span>Created</span><strong>{formatZonedDateTime(post.created_at, post.display_timezone)}</strong></div>
        <div><span>Updated</span><strong>{formatZonedDateTime(post.updated_at, post.display_timezone)}</strong></div>
        <div><span>Scheduling mode</span><strong>{post.attempts[0]?.mode === "facebook_schedule" ? "Facebook" : post.attempts[0] ? "Dry run" : "Not attempted"}</strong></div>
        <div><span>Facebook reference</span><strong>{post.facebook_object_id ?? "Not available"}</strong><small>Set only after confirmed Meta acceptance</small></div>
      </section>

      {post.last_error_message ? (
        <section className="notice notice--error"><div className="notice__icon">!</div><div><h3>{post.last_error_code}</h3><p>{post.last_error_message}</p></div></section>
      ) : null}

      <section className="section-panel">
        <div className="section-heading"><div><span className="eyebrow">Immutable attempt history</span><h2>Scheduling attempts</h2></div><span className="phase-badge">{post.attempts.length} total</span></div>
        {post.attempts.length === 0 ? (
          <p className="muted-copy">No scheduling attempts have been recorded.</p>
        ) : (
          <div className="attempt-list">
            {post.attempts.map((attempt) => (
              <article className="attempt-row" key={attempt.id}>
                <div><AttemptStatusBadge result={attempt.result} /><strong>{attempt.mode === "facebook_schedule" ? "Facebook scheduling" : "Dry run · simulated"}</strong><p>{attempt.safe_message}</p></div>
                <div className="attempt-row__meta"><span>{formatZonedDateTime(attempt.created_at, post.display_timezone)}</span><small>External request: {attempt.external_request_made ? "Yes" : "No"}</small></div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
