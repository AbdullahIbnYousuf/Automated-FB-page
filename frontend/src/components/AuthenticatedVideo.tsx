import { useEffect, useState } from "react";

import { apiBlobRequest } from "../api/client";

export function AuthenticatedVideo({ path }: { path: string }) {
  const [preview, setPreview] = useState<{ path: string; url: string | null } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    void apiBlobRequest(path, true, controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setPreview({ path, url: objectUrl });
    }).catch(() => {
      if (!controller.signal.aborted) setPreview({ path, url: null });
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (preview?.path !== path) return <p role="status">Loading private video…</p>;
  if (!preview.url) return <p role="status">The private video could not be loaded.</p>;
  return <video src={preview.url} controls playsInline aria-label="Saved video preview" />;
}
