import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { listPosts } from "../api/posts";
import { AuthenticatedImage } from "../components/AuthenticatedImage";
import { AttemptStatusBadge, PostStatusBadge } from "../components/PostStatusBadge";
import type { PostRecord } from "../types/post";
import { formatZonedDateTime } from "../utils/datetime";

export function PostsPage() {
  const [posts, setPosts] = useState<PostRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPosts((await listPosts()).items);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Posts could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page-stack">
      <section className="section-panel section-panel--intro compact-intro list-heading">
        <div>
          <span className="eyebrow">Content queue</span>
          <h2>Posts</h2>
          <p>Every item shown here is stored in Supabase PostgreSQL.</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void load()}>
          Refresh
        </button>
      </section>

      {error ? (
        <section className="notice notice--error" role="alert">
          <div className="notice__icon">!</div>
          <div><h3>Posts unavailable</h3><p>{error}</p></div>
        </section>
      ) : null}

      {loading ? (
        <section className="empty-state"><div className="empty-state__mark">…</div><h2>Loading posts</h2></section>
      ) : posts.length === 0 ? (
        <section className="empty-state">
          <div className="empty-state__mark">0</div>
          <h2>No posts yet</h2>
          <p>Create a draft and it will remain available after refresh or restart.</p>
          <Link className="primary-button primary-button--link" to="/new-post">Create your first post</Link>
        </section>
      ) : (
        <section className="posts-list" aria-label="Saved posts">
          {posts.map((post) => {
            const latestAttempt = post.attempts[0];
            return (
              <Link className="post-row" to={`/posts/${post.id}`} key={post.id}>
                <AuthenticatedImage path={post.image_url} alt="" className="post-row__image" />
                <div className="post-row__body">
                  <div className="post-row__badges">
                    <PostStatusBadge status={post.status} />
                    {latestAttempt ? <AttemptStatusBadge result={latestAttempt.result} /> : null}
                  </div>
                  <h3>{post.caption}</h3>
                  <p>
                    {formatZonedDateTime(post.scheduled_for_utc, post.display_timezone)} · {post.display_timezone}
                  </p>
                  {latestAttempt ? (
                    <small>Latest dry run: {latestAttempt.safe_message}</small>
                  ) : (
                    <small>No dry-run attempt yet</small>
                  )}
                </div>
                <span className="post-row__arrow">→</span>
              </Link>
            );
          })}
        </section>
      )}
    </div>
  );
}
