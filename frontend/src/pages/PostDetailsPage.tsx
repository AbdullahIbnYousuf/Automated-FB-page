import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { getPost, schedulePost, updatePost } from "../api/posts";
import { AuthenticatedImage } from "../components/AuthenticatedImage";
import { AttemptStatusBadge, PostStatusBadge } from "../components/PostStatusBadge";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { PostRecord, ScheduleResult } from "../types/post";
import {
  formPartsFromLocalIso,
  formatUtcDateTime,
  formatZonedDateTime,
  joinLocalDateTime,
} from "../utils/datetime";

export function PostDetailsPage() {
  const { postId } = useParams();
  const { status: systemStatus } = useSystemStatus();
  const [post, setPost] = useState<PostRecord | null>(null);
  const [caption, setCaption] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [loading, setLoading] = useState(Boolean(postId));
  const [saving, setSaving] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scheduleResult, setScheduleResult] = useState<ScheduleResult | null>(null);
  const realSchedulingEnabled = systemStatus?.publishing_enabled === true;

  const applyPost = useCallback((record: PostRecord) => {
    const parts = formPartsFromLocalIso(record.scheduled_for_local);
    setPost(record);
    setCaption(record.caption);
    setDate(parts.date);
    setTime(parts.time);
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

  async function runSchedule() {
    if (!post) return;
    setScheduling(true);
    setError(null);
    setNotice(null);
    try {
      const result = await schedulePost(post.id);
      setScheduleResult(result);
      applyPost(await getPost(post.id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Scheduling failed safely.");
      await load();
    } finally {
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
    systemStatus?.publish_mode === "facebook_schedule" && !realSchedulingEnabled;

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
          <AuthenticatedImage path={post.image_url} alt="Uploaded post" />
          <div><span>Stored image</span><strong>{post.original_filename}</strong><small>{post.image_mime_type}</small></div>
        </section>

        <section className="composer-panel detail-editor">
          <div className="field-group">
            <label htmlFor="detail-caption">Caption</label>
            <textarea id="detail-caption" rows={7} value={caption} onChange={(event) => setCaption(event.target.value)} disabled={editBlocked || saving} />
          </div>
          <div className="schedule-fields">
            <div className="field-group"><label htmlFor="detail-date">Date</label><input id="detail-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} disabled={editBlocked || saving} /></div>
            <div className="field-group"><label htmlFor="detail-time">Time</label><input id="detail-time" type="time" value={time} onChange={(event) => setTime(event.target.value)} disabled={editBlocked || saving} /></div>
          </div>
          <div className="timezone-callout"><span>Configured timezone</span><strong>{post.display_timezone}</strong><small>Browser timezone is not used for interpretation.</small></div>
          <div className="composer-actions">
            <button className="secondary-button" type="button" disabled={editBlocked || saving || scheduling} onClick={() => void saveEdits()}>{saving ? "Saving…" : "Save Changes"}</button>
            <button className="primary-button" type="button" disabled={editBlocked || saving || scheduling || !systemStatus || realModeBlocked} onClick={() => void runSchedule()}>
              {scheduling
                ? realSchedulingEnabled
                  ? "Scheduling on Facebook…"
                  : "Running simulation…"
                : realSchedulingEnabled
                  ? "Schedule on Facebook"
                  : "Run Dry-Run Schedule"}
            </button>
          </div>
          <p className={`safety-copy${realSchedulingEnabled ? " safety-copy--enabled" : ""}`}>
            {unknownOutcome
              ? "Outcome unknown: check Meta before any further action."
              : realSchedulingEnabled
                ? "Facebook publishing enabled. This action creates one scheduled Page photo."
                : "Dry run: no Facebook request will be sent."}
          </p>
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
