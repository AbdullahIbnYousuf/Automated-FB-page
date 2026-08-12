import { PublicPageLayout, SUPPORT_EMAIL } from "../components/PublicPageLayout";

export function DataDeletionPage() {
  return (
    <PublicPageLayout
      eyebrow="Operator support"
      title="Data deletion instructions"
      introduction="The authorized operator can use these instructions to request deletion of data stored by The Test Lab Operations."
    >
      <section>
        <h2>How to request deletion</h2>
        <ol>
          <li>
            Email <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a> from the
            authorized operator email account.
          </li>
          <li>
            Use the subject <strong>Data deletion request — The Test Lab Operations</strong>.
          </li>
          <li>
            Describe whether the request covers all application data or specific post
            records. Internal post identifiers may be included when available.
          </li>
        </ol>
        <p>
          Do not send a password, Supabase session, Facebook access token, or any other
          credential. The maintainer may request enough non-secret information to
          verify that the request came from the authorized operator.
        </p>
      </section>

      <section>
        <h2>Application data that may be deleted</h2>
        <p>A verified request may cover:</p>
        <ul>
          <li>stored post records and captions;</li>
          <li>uploaded images in private application Storage;</li>
          <li>scheduling-attempt records and safe error metadata; and</li>
          <li>associated application operational data within the requested scope.</li>
        </ul>
      </section>

      <section>
        <h2>Facebook data is separate</h2>
        <p>
          This page provides request instructions; it does not automatically delete
          application data or data held by Facebook. Content or records controlled by
          Meta must be managed through the applicable Meta or Facebook tools. An
          application-data deletion request does not by itself remove Facebook&apos;s own
          copies or records.
        </p>
      </section>

      <section className="legal-callout">
        <h2>Need help?</h2>
        <p>
          Contact <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a> and state
          that the request concerns The Test Lab Operations.
        </p>
      </section>
    </PublicPageLayout>
  );
}
