import { test } from "node:test";
import assert from "node:assert/strict";
import { createDeviceStateQuery } from "../dist/device-state.js";

const code = result => JSON.parse(result.content[0].text).code;
const state = { deviceStates: [{ entity: { entityId: "synthetic" }, capabilityStates: ["synthetic"] }], errors: [] };
const run = (query, error, body) => query(cb => cb(error, body));

test("valid device state retains the existing response format", async () => {
  const result = await run(createDeviceStateQuery(), null, state);
  assert.equal(result.isError, undefined);
  assert.deepEqual(JSON.parse(result.content[0].text), state);
});

test("throttling JSON, callback errors and nested device errors become safe MCP errors", async () => {
  for (const [error, body] of [
    [null, { message: "Too many requests: synthetic-private-value" }],
    [null, { message: "ThrottlingException" }],
    [null, { statusCode: 429 }],
    [new Error("Rate exceeded: synthetic-private-value"), undefined],
    [null, { deviceStates: [], errors: [{ code: "THROTTLING_EXCEPTION" }] }],
  ]) {
    const result = await run(createDeviceStateQuery(), error, body);
    assert.equal(result.isError, true);
    assert.equal(code(result), "RATE_LIMITED");
    assert.ok(!JSON.stringify(result).includes("synthetic-private-value"));
  }
});

test("malformed or unexpected response is never a successful state", async () => {
  for (const body of [null, undefined, {}, [], { message: "synthetic-private-value" },
    { deviceStates: [], errors: null }, { deviceStates: [null], errors: [] },
    { ...state, message: "unexpected failure" }]) {
    const result = await run(createDeviceStateQuery(), null, body);
    assert.equal(result.isError, true);
    assert.equal(code(result), "INVALID_STATE_RESPONSE");
    assert.ok(!JSON.stringify(result).includes("synthetic-private-value"));
  }
});

test("empty state and endpoint errors, including partial results, fail closed", async () => {
  for (const body of [
    { deviceStates: [], errors: [] },
    { deviceStates: [], errors: [{ code: "ENDPOINT_UNREACHABLE", message: "synthetic-private-value" }] },
    { ...state, errors: [{ code: "NO_SUCH_ENDPOINT" }] },
  ]) {
    const result = await run(createDeviceStateQuery(), null, body);
    assert.equal(result.isError, true);
    assert.equal(code(result), "DEVICE_STATE_UNAVAILABLE");
    assert.ok(!JSON.stringify(result).includes("synthetic-private-value"));
  }
});

test("callback failure and synchronous throw are sanitized", async () => {
  const query = createDeviceStateQuery();
  const first = await run(query, new Error("synthetic-private-value"));
  const second = await query(() => { throw new Error("synthetic-private-value"); });
  for (const result of [first, second]) {
    assert.equal(result.isError, true);
    assert.equal(code(result), "STATE_REQUEST_FAILED");
    assert.ok(!JSON.stringify(result).includes("synthetic-private-value"));
  }
});

test("rate-limit cooldown prevents calls until expiry", async () => {
  let now = 1000;
  const query = createDeviceStateQuery({ now: () => now, cooldownMs: 100 });
  assert.equal(code(await run(query, null, { message: "Too many requests" })), "RATE_LIMITED");
  const blocked = await query(() => assert.fail("must not call upstream"));
  assert.equal(code(blocked), "STATE_COOLDOWN");
  now += 100;
  assert.equal((await run(query, null, state)).isError, undefined);
});

test("upstream timeout returns safe error and applies cooldown", async () => {
  const query = createDeviceStateQuery();
  assert.equal(code(await run(query, new Error("Timeout"))), "STATE_TIMEOUT");
  assert.equal(code(await query(() => assert.fail("must not invoke"))), "STATE_COOLDOWN");
});

test("concurrent state query is rejected without a second upstream request", async () => {
  const query = createDeviceStateQuery();
  let done;
  const first = query(cb => { done = cb; });
  assert.equal(code(await query(() => assert.fail("must not invoke"))), "STATE_QUERY_BUSY");
  done(null, state);
  assert.equal((await first).isError, undefined);
});

test("deadline bounds reply but keeps outstanding upstream work isolated", async () => {
  let now = 1000;
  let done;
  const query = createDeviceStateQuery({ deadlineMs: 15, cooldownMs: 100, now: () => now });
  const result = await query(cb => { done = cb; });
  assert.equal(code(result), "STATE_TIMEOUT");
  now += 200;
  assert.equal(code(await query(() => assert.fail("must not invoke"))), "STATE_QUERY_BUSY");
  done(null, { message: "Too many requests" });
  assert.equal(code(await query(() => assert.fail("must not invoke"))), "STATE_COOLDOWN");
  now += 100;
  assert.equal((await run(query, null, state)).isError, undefined);
});

test("duplicate callback cannot release a later request", async () => {
  const query = createDeviceStateQuery();
  let oldDone, newDone;
  await query(cb => { oldDone = cb; cb(null, state); });
  const pending = query(cb => { newDone = cb; });
  oldDone(null, state);
  assert.equal(code(await query(() => assert.fail("must not invoke"))), "STATE_QUERY_BUSY");
  newDone(null, state);
  assert.equal((await pending).isError, undefined);
});
