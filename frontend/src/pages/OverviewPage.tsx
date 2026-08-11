import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, mediaUrl } from "../api/client";
import { listPosts } from "../api/posts";
import { PostStatusBadge } from "../components/PostStatusBadge";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { PostRecord } from "../types/post";
import { formatZonedDateTime } from "../utils/datetime";

function readableMode(mode: string): string {
  return mode.replaceAll("_", " ");
}

export function OverviewPage() {
  const { backendState, status, refresh: refreshSystem } = useSystemStatus();
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [postError, setPostError] = useState<string | null>(null);

  const loadPosts = useCallback(async () => {
    try {
      setPosts((await listPosts()).items);
      setPostError(null);
    } catch (caught) {
      setPostError(caught instanceof ApiError ? caught.message : "Local posts could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void loadPosts();
  }, [loadPosts]);

  const counts = useMemo(
    () => ({
      total: posts.length,
      drafts: posts.filter((post) => post.status === "draft").length,
      ready: posts.filter((post) => post.status === "ready").length,
      dryRuns: posts.reduce(
        (total, post) =>
          total + post.attempts.filter((attempt) => attempt.result === "success").length,
        0,
      ),
    }),
    [posts],
  );

  async function refreshAll() {
    await Promise.all([refreshSystem(), loadPosts()]);
  }

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Local operations snapshot</span>
          <h2>Control content before anything reaches Facebook.</h2>
          <p>
            Drafts, images, schedules, and dry-run attempts remain in local storage.
            Simulation validates the workflow without an external write.
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void refreshAll()}>
          Refresh status
        </button>
      </section>

      {backendState === "unavailable" || postError ? (
        <section className="notice notice--error" role="alert">
          <div className="notice__icon">!</div>
          <div><h3>Backend data unavailable</h3><p>{postError ?? "Start the FastAPI server, then refresh. No healthy state is being assumed."}</p></div>
        </section>
      ) : null}

      <section className="status-grid" aria-label="System and local post status">
        <article className="status-card"><span className="status-card__label">Backend</span><strong>{backendState === "available" ? "Online" : backendState === "loading" ? "Checking" : "Unavailable"}</strong><small>FastAPI service</small></article>
        <article className="status-card"><span className="status-card__label">Publish mode</span><strong>{status ? readableMode(status.publish_mode) : "Unknown"}</strong><small>Reported by backend</small></article>
        <article className="status-card"><span className="status-card__label">Local posts</span><strong>{counts.total}</strong><small>Persisted records</small></article>
        <article className="status-card"><span className="status-card__label">Drafts</span><strong>{counts.drafts}</strong><small>Awaiting dry-run validation</small></article>
        <article className="status-card"><span className="status-card__label">Ready</span><strong>{counts.ready}</strong><small>Locally validated, not Facebook-scheduled</small></article>
        <article className="status-card"><span className="status-card__label">Dry runs completed</span><strong>{counts.dryRuns}</strong><small>Simulated successes</small></article>
        <article className="status-card"><span className="status-card__label">Timezone</span><strong>{status?.timezone ?? "Unknown"}</strong><small>Explicit operator timezone</small></article>
        <article className="status-card"><span className="status-card__label">Facebook configuration</span><strong>{status ? status.facebook.fully_configured ? "Configured" : "Not configured" : "Unknown"}</strong><small>Presence only; no connection call</small></article>
      </section>

      <section className="section-panel">
        <div className="section-heading"><div><span className="eyebrow">Recent local records</span><h2>{posts.length ? "Latest posts" : "Nothing is waiting yet"}</h2></div><Link className="secondary-button secondary-button--link" to="/posts">View all posts</Link></div>
        {posts.length === 0 ? (
          <p className="muted-copy">Create a draft to begin the local content workflow.</p>
        ) : (
          <div className="recent-posts">
            {posts.slice(0, 3).map((post) => (
              <Link to={`/posts/${post.id}`} className="recent-post" key={post.id}>
                <img src={mediaUrl(post.image_url)} alt="" />
                <div><PostStatusBadge status={post.status} /><strong>{post.caption}</strong><small>{formatZonedDateTime(post.scheduled_for_utc, post.display_timezone)}</small></div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
