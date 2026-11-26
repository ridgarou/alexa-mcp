import net from "node:net";
import https from "node:https";
import dns from "node:dns/promises";
import dgram from "node:dgram";

const [proxy, gateway, mode] = process.argv.slice(2);
let failures = 0;

// Emit only fixed test identifiers and bounded status codes, even on failure.
// Never print response bodies, headers, raw exception messages or destinations.
function outcome(id, actual, expected) {
  const values = Array.isArray(expected) ? expected : [expected];
  const ok = values.includes(actual);
  if (!ok) failures++;
  console.log(`PROBE ${id} ${ok ? "PASS" : "FAIL"} ${actual}`);
  return ok;
}

function safeCode(err) {
  return typeof err?.code === "string" && /^[A-Z0-9_]{1,40}$/.test(err.code)
    ? err.code : "UNKNOWN";
}

function socketAttempt(host, port, payload) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    let buffer = "";
    let settled = false;
    const deadline = setTimeout(() => done("TIMEOUT"), 3000);
    function done(result) {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      s.destroy();
      resolve(result);
    }
    s.once("error", err => done("SOCKET_" + safeCode(err)));
    s.once("connect", () => {
      if (!payload) return done("CONNECTED");
      s.write(payload);
    });
    s.on("data", chunk => {
      buffer += chunk.toString("ascii");
      const end = buffer.indexOf("\r\n");
      if (end !== -1) {
        const match = buffer.slice(0, end).match(/^HTTP\/1\.[01] ([1-5]\d{2})(?: |$)/);
        done(match ? "HTTP_" + match[1] : "INVALID");
      } else if (buffer.length > 4096) done("INVALID");
    });
    s.once("end", () => done("CLOSED"));
  });
}
function connectTo(authority) {
  return "CONNECT " + authority + " HTTP/1.1\r\nHost: " + authority + "\r\n\r\n";
}

const denied = [
  ["PROXY_UNKNOWN", "example.invalid:443"],
  ["PROXY_PUBLIC_IP", "1.1.1.1:443"],
  ["PROXY_GATEWAY_IP", gateway + ":443"],
  ["PROXY_LOOPBACK", "127.0.0.1:443"],
  ["PROXY_WRONG_PORT", "alexa.amazon.es:80"],
  ["PROXY_SUFFIX_TRICK", "alexa.amazon.es.example.invalid:443"],
  ["PROXY_IPV6_LITERAL", "[::1]:443"],
];
for (const [id, authority] of denied) {
  outcome(id, await socketAttempt(proxy, 3128, connectTo(authority)), "HTTP_403");
}
outcome("PROXY_PLAIN_HTTP", await socketAttempt(proxy, 3128,
  "GET http://alexa.amazon.es/ HTTP/1.1\r\nHost: alexa.amazon.es\r\n\r\n"), "HTTP_403");

// No route and timeout are both valid negative observations; connection
// refusal alone does not demonstrate that a firewall blocked the packet.
const blocked = ["TIMEOUT", "SOCKET_ENETUNREACH", "SOCKET_EHOSTUNREACH"];
for (const [id, host, port] of [
  ["DIRECT_PUBLIC", "1.1.1.1", 443],
  ["DIRECT_GATEWAY", gateway, 443],
  ["DIRECT_DOCKER_DNS_TCP", "127.0.0.11", 53],
  ["DIRECT_PUBLIC_DNS_TCP", "1.1.1.1", 53],
  ["DIRECT_IPV6", "::1", 443],
]) {
  outcome(id, await socketAttempt(host, port), blocked);
}
// A real DNS query on a plain UDP socket. c-ares can collapse local
// routing/firewall errors into ECONNREFUSED; it is not our only evidence.
function udpDnsAttempt(server) {
  return new Promise(resolve => {
    const socket = dgram.createSocket("udp4");
    const query = Buffer.from("123401000001000000000000076578616d706c6503636f6d0000010001", "hex");
    let settled = false;
    const deadline = setTimeout(() => done("UDP_TIMEOUT"), 1200);
    function done(result) {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      try { socket.close(); } catch {}
      resolve(result);
    }
    socket.once("message", () => done("UDP_RESPONSE"));
    socket.once("error", err => done("UDP_" + safeCode(err)));
    socket.send(query, 53, server, err => {
      if (err) done("UDP_" + safeCode(err));
    });
  });
}
for (const [id, server] of [
  ["DIRECT_DOCKER_DNS_UDP", "127.0.0.11"],
  ["DIRECT_PUBLIC_DNS_UDP", "1.1.1.1"],
]) {
  const raw = await udpDnsAttempt(server);
  const resolver = new dns.Resolver({ timeout: 500, tries: 1 });
  resolver.setServers([server]);
  let actual = "RESOLVED";
  try {
    await resolver.resolve4("example.com");
  } catch (e) {
    actual = "DNS_" + safeCode(e);
  } finally {
    resolver.cancel();
  }
  // These are negative socket observations, not proof by themselves.
  // The host independently requires a kernel drop counter or no route.
  const rawBlocked = ["UDP_TIMEOUT", "UDP_EPERM", "UDP_EACCES",
    "UDP_ENETUNREACH", "UDP_EHOSTUNREACH"].includes(raw);
  const resolverBlocked = ["DNS_ETIMEOUT", "DNS_ECONNREFUSED",
    "DNS_ENETUNREACH", "DNS_EHOSTUNREACH", "DNS_EPERM", "DNS_EACCES"].includes(actual);
  const observed = raw + "_" + actual;
  outcome(id, observed, rawBlocked && resolverBlocked ? observed : []);
}

if (mode === "amazon" && failures === 0) {
  const result = await new Promise(resolve => {
    const req = https.get("https://alexa.amazon.es/", { timeout: 15000 }, res => {
      const authorized = res.socket.authorized;
      res.destroy();
      resolve(authorized ? "TLS_VERIFIED" : "TLS_UNVERIFIED");
    });
    req.once("timeout", () => req.destroy(new Error("TIMEOUT")));
    req.once("error", e => resolve("SOCKET_" + safeCode(e)));
  });
  outcome("AMAZON_TLS", result, "TLS_VERIFIED");
}

console.log("PROBE_SUMMARY " + (failures === 0 ? "PASS" : "FAIL") + " " + failures);
process.exitCode = failures === 0 ? 0 : 1;
