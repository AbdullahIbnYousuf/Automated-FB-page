import { Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { PasswordSetupPage } from "./pages/PasswordSetupPage";
import { NewPostPage } from "./pages/NewPostPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PostDetailsPage } from "./pages/PostDetailsPage";
import { PostsPage } from "./pages/PostsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SystemStatusProvider } from "./state/SystemStatusContext";

function AuthenticatedApplication() {
  const { loading, passwordSetupRequired, session } = useAuth();

  if (loading) {
    return <main className="login-page"><p>Checking operator session…</p></main>;
  }
  if (!session) return <LoginPage />;
  if (passwordSetupRequired) return <PasswordSetupPage />;

  return (
    <SystemStatusProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="new-post" element={<NewPostPage />} />
          <Route path="posts" element={<PostsPage />} />
          <Route path="posts/details" element={<PostDetailsPage />} />
          <Route path="posts/:postId" element={<PostDetailsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </SystemStatusProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApplication />
    </AuthProvider>
  );
}
