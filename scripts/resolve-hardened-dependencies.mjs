// One-time migration: run in a clean checkout, then review and commit both manifests.
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const expected = {
  "@modelcontextprotocol/sdk": "1.32.2",
  "alexa-remote2": "8.1.1",
  "zod": "4.6.7"
};
Object.assign(pkg.dependencies, expected);
pkg.overrides = {
  ...pkg.overrides,
  "proxy-addr": "2.0.8",
  "alexa-cookie2": { ".": "5.0.6", "cookie": "0.7.2" }
};
writeFileSync("package.json", JSON.stringify(pkg, null, 2) + "\n");
const env = { ...process.env, npm_config_registry: "https://registry.npmjs.org/", npm_config_ignore_scripts: "true" };
const npm = (args) => execFileSync("npm", args, { env, stdio: "inherit" });
npm(["install", "--package-lock-only", "--ignore-scripts", "--include=dev", "--no-audit", "--no-fund"]);
try {
  npm(["audit", "fix", "--package-lock-only", "--ignore-scripts", "--include=dev", "--no-fund"]);
} catch {
  console.error("Audit fix returned a failure; final audit must pass.");
}
npm(["audit", "--package-lock-only", "--include=dev", "--audit-level=low"]);
const lock = JSON.parse(readFileSync("package-lock.json", "utf8"));
for (const [name, version] of Object.entries(expected)) {
  assert.equal(lock.packages["node_modules/" + name]?.version, version, name);
}
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path) continue;
  assert.equal(new URL(entry.resolved).origin, "https://registry.npmjs.org", path);
  assert.ok(entry.integrity, path + ": missing integrity");
  assert.ok(!entry.hasInstallScript, path + ": installation script requires review");
  if (path.endsWith("/alexa-cookie2")) assert.equal(entry.version, "5.0.6");
  if (path.endsWith("/cookie")) assert.equal(entry.version, "0.7.2");
  if (path.endsWith("/proxy-addr")) assert.equal(entry.version, "2.0.8");
}
assert.ok(Object.keys(lock.packages).some(p => p.endsWith("/alexa-cookie2")));
console.log("Dependency migration complete. Review and commit package.json and package-lock.json together.");
