import net from "node:net";

const host = process.argv[2];
const socket = net.connect({host, port: 3128});
let data = "";
let finished = false;
function done(label, status = 1) {
  if (finished) return;
  finished = true;
  socket.destroy();
  console.log(label);
  process.exitCode = status;
}
socket.setTimeout(1500, () => done("TIMEOUT"));
socket.once("error", err => {
  const code = typeof err.code === "string" && /^[A-Z0-9_]+$/.test(err.code)
    ? err.code : "UNKNOWN";
  done("SOCKET_" + code);
});
socket.once("connect", () => {
  socket.write("CONNECT example.invalid:443 HTTP/1.1\r\nHost: example.invalid:443\r\n\r\n");
});
socket.on("data", chunk => {
  data += chunk.toString("ascii");
  const end = data.indexOf("\r\n");
  if (end !== -1) {
    const m = data.slice(0, end).match(/^HTTP\/1\.[01] ([1-5]\d{2})(?: |$)/);
    if (!m) return done("INVALID");
    done("HTTP_" + m[1], m[1] === "403" ? 0 : 1);
  } else if (data.length > 4096) done("INVALID");
});
socket.once("end", () => done("CLOSED"));
