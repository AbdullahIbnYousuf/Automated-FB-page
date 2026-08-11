import { useEffect, useState } from "react";

import { apiBlobRequest } from "../api/client";

export function AuthenticatedImage({
  path,
  alt,
  className,
}: {
  path: string;
  alt: string;
  className?: string;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    void apiBlobRequest(path)
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (active) setObjectUrl(null);
      });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [path]);

  return (
    <img
      src={objectUrl ?? undefined}
      alt={alt}
      className={className}
      aria-busy={!objectUrl}
    />
  );
}
