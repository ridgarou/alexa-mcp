import assert from "node:assert/strict";
import { test } from "node:test";
import { chmodSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadAuth, saveAuth, hasAuth } from "../dist/store.js";

function fixture(t) {
  const dir = mkdtempSync(join(tmpdir(), "alexa-store-test-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return { dir, path: join(dir, "alexa.json") };
}

test("stores synthetic registration data and replaces insecure file permissions", t => {
  const { dir, path } = fixture(t);
  assert.equal(hasAuth(path), false);
  saveAuth({ synthetic: "first" }, path);
  assert.deepEqual(loadAuth(path), { synthetic: "first" });
  if (process.platform !== "win32") {
    chmodSync(path, 0o644);
  }
  saveAuth({ synthetic: "second" }, path);
  assert.deepEqual(loadAuth(path), { synthetic: "second" });
  if (process.platform !== "win32") {
    assert.equal(statSync(path).mode & 0o777, 0o600);
  }
  assert.deepEqual(readdirSync(dir), ["alexa.json"]);
});

test("serialization errors preserve the previous registration", t => {
  const { dir, path } = fixture(t);
  saveAuth({ synthetic: "previous" }, path);
  const previous = readFileSync(path, "utf8");
  const circular = {};
  circular.self = circular;
  assert.throws(() => saveAuth(circular, path), /Unable to persist/);
  assert.throws(() => saveAuth({}, path), /Unable to persist/);
  assert.equal(readFileSync(path, "utf8"), previous);
  assert.deepEqual(readdirSync(dir), ["alexa.json"]);
});

test("rejects malformed and non-object registration data", t => {
  const { path } = fixture(t);
  for (const content of ["not-json", "null", "[]", "{}", "123"]) {
    writeFileSync(path, content);
    assert.equal(loadAuth(path), undefined);
  }
});

test("does not follow auth symlinks on Linux", { skip: process.platform !== "linux" }, t => {
  const { dir, path } = fixture(t);
  const other = join(dir, "other");
  writeFileSync(other, '{"synthetic":"untouched"}');
  symlinkSync(other, path);
  assert.equal(loadAuth(path), undefined);
  saveAuth({ synthetic: "replacement" }, path);
  assert.equal(readFileSync(other, "utf8"), '{"synthetic":"untouched"}');
  assert.deepEqual(loadAuth(path), { synthetic: "replacement" });
});
