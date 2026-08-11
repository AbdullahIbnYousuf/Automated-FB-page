import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { NewPostPage } from "./pages/NewPostPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PostDetailsPage } from "./pages/PostDetailsPage";
import { PostsPage } from "./pages/PostsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SystemStatusProvider } from "./state/SystemStatusContext";

export default function App() {
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
