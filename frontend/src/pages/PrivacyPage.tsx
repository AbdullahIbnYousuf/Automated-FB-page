import { PublicPageLayout, SUPPORT_EMAIL } from "../components/PublicPageLayout";

export function PrivacyPage() {
  return (
    <PublicPageLayout
      eyebrow="Public information"
      title="Privacy policy"
      introduction="This policy describes how The Test Lab Operations handles information for its current single-operator Facebook Page scheduling workflow."
    >
      <section>
        <h2>What the application is</h2>
        <p>
          The Test Lab Operations is currently a single-operator tool used to manage
          already-created content for The Test Lab Facebook Page. Dashboard access is
          restricted through Supabase Auth. These public policy pages do not require
          authentication and do not display dashboard records.
        </p>
      </section>

      <section>
        <h2>Information handled</h2>
        <p>The application stores the information needed for its current workflow:</p>
        <ul>
          <li>post captions and uploaded images;</li>
          <li>requested scheduling dates, times, and timezone;</li>
          <li>post status, scheduling-attempt metadata, safe error details, and returned Facebook identifiers when available; and</li>
          <li>the authorized operator account information needed for authentication and related operational records.</li>
        </ul>
        <p>
          The application does not currently use Facebook analytics, messages,
          comments, advertising data, or other Facebook information outside the
          connection and scheduling functions described here.
        </p>
      </section>

      <section>
        <h2>How information is used</h2>
        <p>
          Information is used to authenticate the authorized operator, save and
          display prepared posts, validate images and scheduling times, record
          scheduling attempts, diagnose operational failures, test access to the
          configured Page, and schedule content when the operator authorizes that
          action.
        </p>
      </section>

      <section>
        <h2>Hosting and service providers</h2>
        <p>
          Supabase hosts authentication, PostgreSQL application records, and private
          image Storage. Render hosts the FastAPI backend, and Cloudflare Pages hosts
          this frontend. Information is processed by these services as needed to
          operate the application.
        </p>
      </section>

      <section>
        <h2>Facebook and Meta</h2>
        <p>
          The backend stores and uses a Facebook Page ID and Page access token for
          authorized operations. Those credentials remain server-side and are not
          intentionally exposed to frontend users. The backend may communicate with
          Meta&apos;s Graph API to test Page connectivity and to schedule a caption and
          image selected by the Page operator.
        </p>
      </section>

      <section>
        <h2>Retention and deletion</h2>
        <p>
          The application does not currently define an automatic retention schedule.
          Application records remain stored until they are removed by the operator or
          maintainer. The authorized operator may request deletion of stored posts,
          images, scheduling-attempt records, and associated application data by
          following the <a href="/data-deletion">data deletion instructions</a>.
        </p>
      </section>

      <section>
        <h2>Contact</h2>
        <p>
          For privacy or deletion questions, email{" "}
          <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>. Do not include a
          password, access token, or other credential in the request.
        </p>
      </section>
    </PublicPageLayout>
  );
}
