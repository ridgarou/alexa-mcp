import assert from "node:assert/strict";
import { test } from "node:test";
import AlexaRemote from "alexa-remote2";
import { createAlexaRemote, RELOGIN_REQUIRED } from "../dist/alexa.js";

test("noninteractive mode blocks generation even after refresh failure", async () => {
  const remote = createAlexaRemote(false);
  let refreshCalls = 0;
  let networkCalls = 0;
  remote.refreshCookie = callback => {
    refreshCalls++;
    callback(new Error("synthetic refresh failure"), null);
  };
  remote.checkAuthentication = () => {
    networkCalls++;
    throw new Error("unexpected network access");
  };
  const stored = { localCookie: "csrf=synthetic;", tokenDate: 0 };
  try {
    const err = await new Promise(resolve => remote.init({
      cookie: stored,
      formerRegistrationData: stored,
      cookieRefreshInterval: 0,
      usePushConnection: false
    }, resolve));
    assert.equal(err?.message, RELOGIN_REQUIRED);
    assert.equal(refreshCalls, 1);
    assert.equal(networkCalls, 0);
    assert.equal(remote.alexaCookie, undefined);
  } finally {
    remote.stop();
  }
});

test("noninteractive mode blocks missing/invalid cookie generation", async () => {
  const remote = createAlexaRemote(false);
  try {
    const err = await new Promise(resolve => remote.init({
      cookie: { synthetic: true },
      cookieRefreshInterval: 0
    }, resolve));
    assert.equal(err?.message, RELOGIN_REQUIRED);
  } finally {
    remote.stop();
  }
});

test("explicit interactive mode keeps upstream generation method", () => {
  const remote = createAlexaRemote(true);
  assert.equal(remote.generateCookie, AlexaRemote.prototype.generateCookie);
  remote.stop();
});
