import assert from "node:assert/strict";
import { test } from "node:test";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { once } from "node:events";

// Exercise the actual entrypoint and real upstream stop(), without network
// or real credentials. Only the dependency's init and inventory are mocked.
const dependency = import.meta.resolve("alexa-remote2");
const fixture = `
import AlexaRemote from ${JSON.stringify(dependency)};
import https from "node:https";
import http from "node:http";
https.request = http.request = () => { throw new Error("Unexpected network"); };
const mode = process.env.TEST_SHUTDOWN_MODE;
const realStop = AlexaRemote.prototype.stop;
AlexaRemote.prototype.stop = function () {
  realStop.call(this);
  console.error("SYNTHETIC_STOP");
};
let attempts = 0;
AlexaRemote.prototype.init = function (opts, callback) {
  attempts++;
  const complete = () => {
    this.cookieRefreshTimeout = setTimeout(() => {}, opts.cookieRefreshInterval);
    if (mode === "fail" && attempts === 1) callback(new Error("synthetic init failure"));
    else callback();
  };
  if (mode === "pending") {
    console.error("SYNTHETIC_INIT_STARTED");
    setTimeout(complete, 150);
  } else complete();
};
AlexaRemote.prototype.getDevices = function (callback) {
  if (mode === "stuck") setInterval(() => {}, 1000);
  callback(null, { devices: [{ accountName: "synthetic" }] });
};
`;
const preload = "data:text/javascript;base64," + Buffer.from(fixture).toString("base64");

async function scenario(t, mode, action, expectedCode = 0) {
  const dir = mkdtempSync(join(tmpdir(), "alexa-mcp-shutdown-"));
  const auth = join(dir, "alexa.json");
  const original = '{"synthetic":true}';
  writeFileSync(auth, original, { mode: 0o600 });
  const proc = spawn(process.execPath, ["--import", preload, "dist/index.js"], {
    env: { ...process.env, ALEXA_MCP_AUTH_PATH: auth, ALEXA_MCP_ALLOW_WRITE: "0",
      ALEXA_MCP_WS_MQTT: "false", ALEXA_MCP_REFRESH_MS: "345600000",
      TEST_SHUTDOWN_MODE: mode },
    stdio: ["pipe", "pipe", "pipe"],
  });
  const exited = once(proc, "close");
  let stderr = "";
  proc.stderr.on("data", chunk => { stderr += chunk.toString(); });
  const lines = createInterface({ input: proc.stdout });
  const messages = new Map();
  lines.on("line", line => {
    const message = JSON.parse(line);
    messages.set(message.id, message);
  });
  t.after(async () => {
    if (proc.exitCode === null && proc.signalCode === null) proc.kill("SIGKILL");
    await exited;
    lines.close();
    rmSync(dir, { recursive: true, force: true });
  });
  async function until(predicate, timeout = 3000) {
    const end = Date.now() + timeout;
    while (!predicate()) {
      if (Date.now() >= end || proc.exitCode !== null || proc.signalCode !== null)
        throw new Error("Synthetic session did not reach expected stage");
      await new Promise(resolve => setTimeout(resolve, 10));
    }
  }
  function send(message) {
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", ...message }) + "\n");
  }
  send({ id: 1, method: "initialize", params: {
    protocolVersion: "2025-03-26", capabilities: {},
    clientInfo: { name: "synthetic-shutdown", version: "1.0.0" }
  } });
  await until(() => messages.has(1));
  assert.ok(messages.get(1).result);
  send({ method: "notifications/initialized" });
  function inventory(id) {
    send({ id, method: "tools/call", params: { name: "alexa_list_devices", arguments: {} } });
  }
  inventory(2);
  if (mode === "pending") {
    await until(() => stderr.includes("SYNTHETIC_INIT_STARTED"));
  } else {
    await until(() => messages.has(2));
    assert.equal(Boolean(messages.get(2).result.isError), mode === "fail");
    if (mode === "fail") {
      inventory(3);
      await until(() => messages.has(3));
      assert.equal(Boolean(messages.get(3).result.isError), false);
    }
  }
  if (action === "EOF") proc.stdin.end();
  else proc.kill(action);
  const [code, signal] = await exited;
  assert.equal(signal, null);
  assert.equal(code, expectedCode);
  assert.match(stderr, /SYNTHETIC_STOP/);
  if (mode === "pending" || mode === "fail")
    assert.ok(stderr.split("SYNTHETIC_STOP").length >= 3);
  if (mode === "stuck") assert.match(stderr, /Shutdown deadline exceeded/);
  else assert.doesNotMatch(stderr, /Shutdown deadline exceeded/);
  assert.equal(readFileSync(auth, "utf8"), original);
}

test("authenticated MCP exits on EOF with upstream refresh timer cancelled", { timeout: 8000 }, t => scenario(t, "ready", "EOF"));
test("EOF during initialization also stops late refresh timer", { timeout: 8000 }, t => scenario(t, "pending", "EOF"));
test("failed initialization stops resources and a later call may retry", { timeout: 8000 }, t => scenario(t, "fail", "EOF"));
test("SIGTERM closes authenticated MCP with signal exit status", { timeout: 8000, skip: process.platform === "win32" }, t => scenario(t, "ready", "SIGTERM", 143));
test("SIGINT closes authenticated MCP with signal exit status", { timeout: 8000, skip: process.platform === "win32" }, t => scenario(t, "ready", "SIGINT", 130));
test("stuck handle reaches bounded nonzero shutdown rather than hanging", { timeout: 18000 }, t => scenario(t, "stuck", "EOF", 1));
