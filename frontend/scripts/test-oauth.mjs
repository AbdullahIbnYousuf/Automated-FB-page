import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

// Use the existing TypeScript compiler and Node test runner; no test framework dependency.
const source = readFileSync(new URL("../src/auth/oauth-consent.ts", import.meta.url), "utf8");
const javascript = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { loadConsent, decideConsent, chatgptRedirect, passwordSetupReturnUrl } = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
const id = "00000000-0000-4000-8000-000000000001";
const callback = "https://chatgpt.com/connector/oauth/test-callback";
const details = { authorization_id: id, redirect_uri: callback, client: { name: "ChatGPT" }, user: { email: "operator@example.com" }, scope: "email" };

test("operator verification precedes fetching consent details", async () => {
  const calls = [];
  const result = await loadConsent(id, async () => calls.push("verify"), {
    getAuthorizationDetails: async () => { calls.push("details"); return { data: details }; },
  });
  assert.deepEqual(calls, ["verify", "details"]);
  assert.equal(result.authorization_id, id);
});

test("a disallowed operator cannot reach consent or approval", async () => {
  const fail = async () => { throw new Error("Operator forbidden"); };
  const provider = { getAuthorizationDetails: () => assert.fail(), approveAuthorization: () => assert.fail() };
  await assert.rejects(loadConsent(id, fail, provider), /forbidden/);
  await assert.rejects(decideConsent(id, true, fail, provider), /forbidden/);
});

test("denial uses only the provider's returned ChatGPT redirect", async () => {
  let denied = false;
  const result = await decideConsent(id, false, async () => {}, {
    denyAuthorization: async (actualId, options) => {
      assert.equal(actualId, id);
      assert.equal(options.skipBrowserRedirect, true);
      denied = true;
      return { data: { redirect_url: `${callback}?error=access_denied` } };
    },
    approveAuthorization: () => assert.fail(),
  });
  assert.equal(denied, true);
  assert.equal(result, `${callback}?error=access_denied`);
});

test("approval re-verifies authorization and suppresses the provider's automatic redirect", async () => {
  const calls = [];
  const result = await decideConsent(id, true, async () => calls.push("verify"), {
    approveAuthorization: async (_, options) => {
      calls.push("approve");
      assert.equal(options.skipBrowserRedirect, true);
      return { data: { redirect_url: `${callback}?code=one-use-code` } };
    },
  });
  assert.deepEqual(calls, ["verify", "approve"]);
  assert.equal(result, `${callback}?code=one-use-code`);
});

test("expired consent errors are sanitized", async () => {
  await assert.rejects(loadConsent(id, async () => {}, {
    getAuthorizationDetails: async () => ({ error: new Error("provider-private-detail") }),
  }), error => !error.message.includes("provider-private-detail") && error.message.includes("expired"));
});

test("redirects cannot escape the verified ChatGPT callbacks", async () => {
  for (const url of ["javascript:alert(1)", "https://evil.example/callback", "https://chatgpt.com.evil.example/connector/oauth/x", "https://chatgpt.com/other", "https://user:password@chatgpt.com/connector/oauth/x"]) {
    assert.throws(() => chatgptRedirect(url));
  }
  await assert.rejects(loadConsent(id, async () => {}, {
    getAuthorizationDetails: async () => ({ data: { redirect_url: "https://evil.example" } }),
  }));
});

test("invalid authorization IDs cause no provider request", async () => {
  await assert.rejects(loadConsent(null, () => assert.fail(), { getAuthorizationDetails: () => assert.fail() }));
});

test("password setup retains only the consent ID and strips recovery parameters", () => {
  assert.equal(passwordSetupReturnUrl("/oauth/consent", `?authorization_id=${id}&type=recovery&code=secret`), `/oauth/consent?authorization_id=${id}`);
  assert.equal(passwordSetupReturnUrl("/", "?type=recovery&code=secret"), "/");
});
