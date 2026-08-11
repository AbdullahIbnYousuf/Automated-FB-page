import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="empty-state">
      <div className="empty-state__mark">404</div>
      <h2>Page not found</h2>
      <p>The requested dashboard screen does not exist.</p>
      <Link className="secondary-button secondary-button--link" to="/">
        Return to overview
      </Link>
    </section>
  );
}
