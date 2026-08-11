import { NavLink, Outlet, useLocation } from "react-router-dom";

import { ModeBanner } from "./ModeBanner";

const navigationItems = [
  { to: "/", label: "Overview", end: true, marker: "01" },
  { to: "/new-post", label: "New Post", marker: "02" },
  { to: "/posts", label: "Posts", end: true, marker: "03" },
  { to: "/posts/details", label: "Post Details", marker: "04" },
  { to: "/settings", label: "Settings", marker: "05" },
];

const pageTitles: Record<string, string> = {
  "/": "Overview",
  "/new-post": "New Post",
  "/posts": "Posts",
  "/posts/details": "Post Details",
  "/settings": "Settings / Connection",
};

export function AppShell() {
  const location = useLocation();
  const pageTitle =
    pageTitles[location.pathname] ??
    (location.pathname.startsWith("/posts/") ? "Post Details" : "Dashboard");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">F</span>
          <span>
            <strong>Page Operations</strong>
            <small>Local control desk</small>
          </span>
        </div>

        <nav className="navigation" aria-label="Primary navigation">
          <p className="navigation__label">Workspace</p>
          {navigationItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `navigation__item${isActive ? " navigation__item--active" : ""}`
              }
            >
              <span>{item.marker}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footnote">
          <span className="eyebrow">V1 foundation</span>
          <p>Reliable scheduling controls begin with a safe local workflow.</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Facebook Page Operations</span>
            <h1>{pageTitle}</h1>
          </div>
          <ModeBanner />
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
