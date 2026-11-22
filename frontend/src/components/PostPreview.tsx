import { previewLocalDateTime } from "../utils/datetime";

interface PostPreviewProps {
  caption: string;
  imageUrl: string | null;
  video?: boolean;
  date: string;
  time: string;
  timezone: string;
}

export function PostPreview({
  caption,
  imageUrl,
  video = false,
  date,
  time,
  timezone,
}: PostPreviewProps) {
  return (
    <article className="post-preview">
      <header className="post-preview__header">
        <div className="post-preview__avatar">P</div>
        <div>
          <strong>Your Facebook Page</strong>
          <small>Preview only · {timezone || "Timezone unavailable"}</small>
        </div>
      </header>
      <p className={`post-preview__caption${caption.trim() ? "" : " is-placeholder"}`}>
        {caption.trim() || "Your caption preview will appear here."}
      </p>
      <div className="post-preview__media">
        {imageUrl && video ? (
          <video src={imageUrl} controls playsInline aria-label="Selected video preview" />
        ) : imageUrl ? (
          <img src={imageUrl} alt="Selected post preview" />
        ) : (
          <span>{video ? "Select one MP4 video" : "Select one JPEG or PNG image"}</span>
        )}
      </div>
      <footer className="post-preview__schedule">
        <span>Planned local time</span>
        <strong>{previewLocalDateTime(date, time)}</strong>
        <small>{timezone}</small>
      </footer>
    </article>
  );
}
