import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

// Use the existing TypeScript compiler and Node test runner; no test framework dependency.
const source = readFileSync(new URL("../src/auth/oauth-consent.ts", import.meta.url), "utf8");
const javascript = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { loadConsent, decideConsent, oauthRedirect, passwordSetupReturnUrl } = await import(`data:text/javascript;base64,${Buffer.from(javascript).toString("base64")}`);
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

test("redirects cannot escape verified web or native callbacks", async () => {
  for (const url of ["javascript:alert(1)", "https://evil.example/callback", "https://chatgpt.com.evil.example/connector/oauth/x", "https://chatgpt.com/other", "https://user:password@chatgpt.com/connector/oauth/x"]) {
    assert.throws(() => oauthRedirect(url));
  }
  await assert.rejects(loadConsent(id, async () => {}, {
    getAuthorizationDetails: async () => ({ data: { redirect_url: "https://evil.example" } }),
  }));
});

test("native consent accepts only the provider-validated loopback callback", async () => {
  const native = "http://127.0.0.1:45881/callback/test_callback_123";
  const calls = [];
  const result = await loadConsent(id, async () => calls.push("verify"), {
    getAuthorizationDetails: async () => { calls.push("details"); return { data: { ...details, redirect_uri: native } }; },
  });
  assert.deepEqual(calls, ["verify", "details"]);
  assert.equal(result.redirect_uri, native);
  for (const approve of [true, false]) {
    const destination = `${native}?${approve ? "code=one-use-code" : "error=access_denied"}&state=test-state`;
    const decision = async (_, options) => {
      assert.equal(options.skipBrowserRedirect, true);
      return { data: { redirect_url: destination } };
    };
    assert.equal(await decideConsent(id, approve, async () => {}, {
      approveAuthorization: decision, denyAuthorization: decision,
    }), destination);
  }
  assert.equal(oauthRedirect("http://127.0.0.1:45881/callback"), "http://127.0.0.1:45881/callback");
});

test("native callback validation rejects local-network and URL tricks", () => {
  for (const url of [
    "http://localhost:45881/callback", "http://127.0.0.2:45881/callback",
    "http://192.168.1.1:45881/callback", "http://2130706433:45881/callback",
    "http://127.1:45881/callback", "http://127.0.0.1:80/callback",
    "http://127.0.0.1:45881/other", "http://127.0.0.1:45881/callback/short",
    "http://127.0.0.1:45881/callback/test_callback#fragment",
    "http://user:password@127.0.0.1:45881/callback",
    "https://127.0.0.1:45881/callback", "https://chatgpt.com:444/connector/oauth/x",
  ]) assert.throws(() => oauthRedirect(url), url);
});

test("invalid authorization IDs cause no provider request", async () => {
  for (const invalid of [null, "", " ", "../other", "id?query", "id#fragment", "a".repeat(129)]) {
    await assert.rejects(loadConsent(invalid, () => assert.fail(), { getAuthorizationDetails: () => assert.fail() }));
  }
});

test("opaque Supabase authorization IDs survive loading, approval and denial", async () => {
  const opaqueId = "AbCdEfGhIjKlMnOpQrStUvWxYz012345";
  assert.equal(opaqueId.length, 32);
  const calls = [];
  const result = await loadConsent(opaqueId, async () => calls.push("verify"), {
    getAuthorizationDetails: async actualId => {
      assert.equal(actualId, opaqueId);
      calls.push("details");
      return { data: { ...details, authorization_id: opaqueId } };
    },
  });
  assert.deepEqual(calls, ["verify", "details"]);
  assert.equal(result.authorization_id, opaqueId);
  for (const approve of [true, false]) {
    const decision = async actualId => {
      assert.equal(actualId, opaqueId);
      return { data: { redirect_url: callback } };
    };
    assert.equal(await decideConsent(opaqueId, approve, async () => {}, {
      approveAuthorization: decision, denyAuthorization: decision,
    }), callback);
  }
  assert.equal(passwordSetupReturnUrl("/oauth/consent", `?authorization_id=${opaqueId}&code=secret`), `/oauth/consent?authorization_id=${opaqueId}`);
});

test("password setup retains only the consent ID and strips recovery parameters", () => {
  assert.equal(passwordSetupReturnUrl("/oauth/consent", `?authorization_id=${id}&type=recovery&code=secret`), `/oauth/consent?authorization_id=${id}`);
  assert.equal(passwordSetupReturnUrl("/", "?type=recovery&code=secret"), "/");
});


test("bridge callback is exact and preserves existing redirect restrictions", () => {
  const callback = "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback";
  assert.equal(oauthRedirect(callback + "?code=single-use&state=test"), callback + "?code=single-use&state=test");
  for (const invalid of [
    "http://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site.evil.example/oauth/callback",
    "https://other.sassypear13.chatgpt.site/oauth/callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/other",
    callback + "/", callback + "#secret",
    callback + "#", callback + "?code=test#",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site:444/oauth/callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site:443/oauth/callback",
    "https://user:password@facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/other/../callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/other/%2e%2e/oauth/callback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/%63allback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth%2fcallback",
    "https://facebook-scheduler-bridge.sassypear13.chatgpt.site\\oauth\\callback",
    "//facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback",
    " " + callback, callback + "\n", callback.replace("/oauth/", "/oau\tth/"),
  ]) assert.throws(() => oauthRedirect(invalid));
});

test("bridge consent verifies the operator before details, approval and denial", async () => {
  const callback = "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback";
  const calls = [];
  const verify = async () => calls.push("verify");
  const loaded = await loadConsent(id, verify, {
    getAuthorizationDetails: async actualId => {
      assert.equal(actualId, id);
      calls.push("details");
      return { data: { ...details, redirect_uri: callback } };
    },
  });
  assert.equal(loaded.redirect_uri, callback);
  for (const approve of [true, false]) {
    const destination = callback + (approve ? "?code=one-use-code&state=test" : "?error=access_denied&state=test");
    const decision = async (actualId, options) => {
      assert.equal(actualId, id);
      assert.equal(options.skipBrowserRedirect, true);
      calls.push(approve ? "approve" : "deny");
      return { data: { redirect_url: destination } };
    };
    assert.equal(await decideConsent(id, approve, verify, {
      approveAuthorization: decision, denyAuthorization: decision,
    }), destination);
  }
  assert.deepEqual(calls, ["verify", "details", "verify", "approve", "verify", "deny"]);
});

test("already granted bridge consent follows only the provider's validated callback", async () => {
  const destination = "https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback?code=test&state=test";
  const calls = [];
  const result = await loadConsent(id, async () => calls.push("verify"), {
    getAuthorizationDetails: async () => {
      calls.push("details");
      return { data: { redirect_url: destination } };
    },
  });
  assert.deepEqual(calls, ["verify", "details"]);
  assert.equal(result.redirect_url, destination);
});

test("consent refuses a provider-returned bridge callback lookalike at every stage", async () => {
  const evil = "https://facebook-scheduler-bridge.sassypear13.chatgpt.site.evil.example/oauth/callback";
  for (const data of [{ ...details, redirect_uri: evil }, { redirect_url: evil }]) {
    await assert.rejects(loadConsent(id, async () => {}, { getAuthorizationDetails: async () => ({ data }) }));
  }
  for (const approve of [true, false]) {
    const decision = async () => ({ data: { redirect_url: evil } });
    await assert.rejects(decideConsent(id, approve, async () => {}, {
      approveAuthorization: decision, denyAuthorization: decision,
    }));
  }
});
