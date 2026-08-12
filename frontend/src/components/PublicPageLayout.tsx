import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";

export const SUPPORT_EMAIL = "a.a.y.tonmoy@gmail.com";

interface PublicPageLayoutProps {
  eyebrow: string;
  title: string;
  introduction: string;
  children: ReactNode;
}

export function PublicPageLayout({
  eyebrow,
  title,
  introduction,
  children,
}: PublicPageLayoutProps) {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = `${title} — The Test Lab Operations`;
    return () => {
      document.title = previousTitle;
    };
  }, [title]);

  return (
    <div className="legal-page">
      <header className="legal-header">
        <Link className="legal-brand" to="/" aria-label="The Test Lab Operations sign in">
          <span className="brand__mark" aria-hidden="true">F</span>
          <span>
            <strong>The Test Lab Operations</strong>
            <small>Facebook Page operations</small>
          </span>
        </Link>
        <nav className="legal-navigation" aria-label="Public pages">
          <Link to="/privacy">Privacy</Link>
          <Link to="/data-deletion">Data deletion</Link>
          <Link to="/">Operator sign in</Link>
        </nav>
      </header>

      <main className="legal-content">
        <article className="legal-card">
          <div className="legal-title">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{introduction}</p>
            <small>Last updated August 12, 2026</small>
          </div>
          <div className="legal-sections">{children}</div>
        </article>
      </main>

      <footer className="legal-footer">
        <span>The Test Lab Operations</span>
        <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
      </footer>
    </div>
  );
}
