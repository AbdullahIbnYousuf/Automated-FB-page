# Manual Meta Setup — Phase 4

Phase 4 verifies one Facebook Page with a read-only Graph API request. It cannot publish, schedule, edit, upload, or delete Facebook content.

## Current integration

- Graph API version: `v26.0`
- Backend request: `GET /v26.0/{page-id}?fields=id,name`
- Token type: Page access token for the intended Facebook Page
- Relevant read permissions: `pages_show_list` and `pages_read_engagement`
- Future-only permission: `pages_manage_posts`; Phase 4 does not test or prove it

Meta's current permission reference lists `pages_read_engagement` and `pages_show_list` as the Page read/discovery permissions. Meta's Pages guide identifies `pages_manage_posts` for Page post creation, which remains outside Phase 4.

## Human authorization checklist

1. Sign in to [Meta for Developers](https://developers.facebook.com/) with the Facebook account that manages the intended Page.
2. Create or select the Meta developer app that will own this Page integration.
3. Confirm that your Facebook account can manage the intended Page. Future publishing requires the Page's content-creation task, but Phase 4 performs no write.
4. Open Meta's [Graph API Explorer](https://developers.facebook.com/tools/explorer/), select that app, and generate a User access token with `pages_show_list` and `pages_read_engagement`. Do not request comments, messages, ads, analytics, or Instagram permissions.
5. In the Explorer, run `GET /v26.0/me/accounts?fields=id,name,access_token,tasks` and locate the one intended Page. The returned Page entry supplies its Page ID and Page access token.
6. In the Render service dashboard, add the Page ID as `FACEBOOK_PAGE_ID` and the Page token as `FACEBOOK_PAGE_ACCESS_TOKEN`. Keep `FACEBOOK_GRAPH_API_VERSION=v26.0`.
7. Save the Render environment changes and allow the backend to restart.
8. Sign in to the hosted dashboard, open **Settings / Connection**, and press **Test Facebook Connection**.
9. Confirm that the returned Page name and ID are the intended Page. The UI must still say publishing capability has not been proven.

Never paste the Page token into source files, Cloudflare Pages, Supabase, screenshots, logs, issues, or chat. A short-lived token can expire; if the dashboard reports expired credentials, generate a replacement through Meta and update only Render.

Official references:

- [Meta Pages API getting started](https://developers.facebook.com/docs/pages-api/getting-started/)
- [Meta Page Graph API reference](https://developers.facebook.com/docs/graph-api/reference/page/)
- [Meta access tokens](https://developers.facebook.com/documentation/facebook-login/guides/access-tokens/)
- [Meta pages_read_engagement permission](https://developers.facebook.com/docs/permissions/reference/pages_read_engagement/)
