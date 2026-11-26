import net from "node:net";
import tls from "node:tls";
import https from "node:https";
import dns from "node:dns/promises";
import assert from "node:assert/strict";

const [proxy, gateway, mode] = process.argv.slice(2);
function socketAttempt(host, port, payload) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    let buffer = "";
    const done = (result) => { s.destroy(); resolve(result); };
    s.setTimeout(1800, () => done("BLOCKED"));
    s.once("error", () => done("BLOCKED"));
    s.once("connect", () => {
      if (!payload) return done("CONNECTED");
      s.write(payload);
    });
    s.on("data", (chunk) => {
      buffer += chunk.toString("ascii");
      const match = buffer.match(/^HTTP\/1\.[01] (\d{3})\b/);
      if (match) done(match[1]);
      if (buffer.length > 4096) done("INVALID");
    });
    s.once("end", () => done("CLOSED"));
  });
}
function connectTo(authority) {
  return "CONNECT " + authority + " HTTP/1.1\r\nHost: " + authority + "\r\n\r\n";
}
for (const authority of [
  "example.invalid:443", "1.1.1.1:443", gateway + ":443",
  "127.0.0.1:443", "alexa.amazon.es:80",
  "alexa.amazon.es.example.invalid:443", "[::1]:443"
]) {
  assert.equal(await socketAttempt(proxy, 3128, connectTo(authority)), "403", "Unexpected proxy result");
}
assert.equal(await socketAttempt(proxy, 3128,
  "GET http://alexa.amazon.es/ HTTP/1.1\r\nHost: alexa.amazon.es\r\n\r\n"), "403");
console.log("PASS: proxy denies unknown domains, IP literals, wrong ports and plain HTTP");

for (const [host, port] of [["1.1.1.1",443],[gateway,443],
  ["127.0.0.11",53],["1.1.1.1",53],["::1",443]]) {
  assert.equal(await socketAttempt(host, port), "BLOCKED", "Direct socket unexpectedly connected");
}
for (const server of ["127.0.0.11","1.1.1.1"]) {
  const resolver = new dns.Resolver({ timeout: 500, tries: 1 });
  resolver.setServers([server]);
  try {
    await resolver.resolve4("example.com");
    throw new Error("DNS_UNEXPECTED_SUCCESS");
  } catch (e) {
    // NXDOMAIN/refused from a reachable resolver is not proof of network blocking.
    assert.equal(e.code, "ETIMEOUT", "DNS did not time out");
  }
}
console.log("PASS: direct public, gateway, IPv6 and DNS probes blocked");

if (mode === "amazon") {
  await new Promise((resolve, reject) => {
    const req = https.get("https://alexa.amazon.es/", { timeout: 15000 }, res => {
      try {
        assert.equal(res.socket.authorized, true);
        res.destroy();
        resolve();
      } catch (e) { reject(e); }
    });
    req.once("timeout", () => req.destroy(new Error("TIMEOUT")));
    req.once("error", reject);
  });
  console.log("PASS: native Node HTTPS proxy path with verified Amazon TLS (no authentication)");
}
