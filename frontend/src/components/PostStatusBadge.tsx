import type { AttemptResult, PostStatus } from "../types/post";

export function PostStatusBadge({ status }: { status: PostStatus }) {
  return <span className={`status-pill status-pill--${status}`}>{status}</span>;
}

export function AttemptStatusBadge({ result }: { result: AttemptResult }) {
  return (
    <span className={`attempt-pill attempt-pill--${result}`}>
      {result.replaceAll("_", " ")}
    </span>
  );
}
