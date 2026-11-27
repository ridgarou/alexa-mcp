/**
 * Stdio EOF is the lifetime boundary for this on-demand server.
 * The upstream remote owns timers and possibly active requests; cancel its
 * periodic work and let existing callbacks drain naturally. A stuck handle
 * must not keep an authenticated container alive indefinitely.
 */
export function installShutdown(session: AbortController, closeTransport: () => Promise<void>): void {
  let closing = false;
  function shutdown(code: number): void {
    if (closing) return;
    closing = true;
    if (code !== 0 || process.exitCode === undefined) process.exitCode = code;
    const deadline = setTimeout(() => {
      console.error("[alexa-mcp] Shutdown deadline exceeded. Details suppressed.");
      process.exit(1);
    }, 10_000);
    // The timer is only a fallback, not a reason to keep the process alive.
    deadline.unref();
    session.abort();
    void Promise.resolve().then(closeTransport).catch(() => {
      console.error("[alexa-mcp] Transport close failed. Details suppressed.");
      process.exitCode = 1;
    });
  }

  process.stdin.once("end", () => shutdown(0));
  process.stdin.once("close", () => shutdown(0));
  process.stdin.once("error", () => shutdown(1));
  process.once("SIGINT", () => shutdown(130));
  process.once("SIGTERM", () => shutdown(143));
}
