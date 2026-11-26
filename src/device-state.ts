// Bound MCP waiting independently of alexa-remote2's internal retry timer.
// No credentials, upstream error messages or device identifiers enter failures.
const DEFAULT_DEADLINE_MS = 25_000;
const DEFAULT_COOLDOWN_MS = 60_000;

type Result = {
  content: [{ type: "text"; text: string }];
  isError?: true;
};
type Invoke = (callback: (error: unknown, body?: unknown) => void) => void;

function failure(code: string, message: string): Result {
  return { isError: true, content: [{ type: "text", text: JSON.stringify({ code, message }) }] };
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function throttled(value: unknown): boolean {
  return typeof value === "string" &&
    /throttl|too many requests|rate[ _-]?exceeded|rate[ _-]?limit|(?:^|\D)429(?:\D|$)/i.test(value);
}

function errorFields(value: unknown): boolean {
  if (throttled(value)) return true;
  if (!object(value)) return false;
  return [value.message, value.code, value.errorCode, value.errorType,
    value.errorMessage, value.status, value.statusCode, value.error]
    .some(v => throttled(v) || v === 429);
}

function classify(error: unknown, body: unknown): { result: Result; cooldown: boolean } {
  const rateLimited = errorFields(error) || errorFields(body) ||
    (object(body) && Array.isArray(body.errors) && body.errors.some(errorFields));
  if (rateLimited) {
    return { result: failure("RATE_LIMITED", "Amazon limited device-state queries. Do not retry immediately."), cooldown: true };
  }
  if (error != null) {
    const message = object(error) ? error.message : error;
    if (typeof message === "string" && /timeout|timed out/i.test(message)) {
      return { result: failure("STATE_TIMEOUT", "Device-state request timed out. Do not retry immediately."), cooldown: true };
    }
    return { result: failure("STATE_REQUEST_FAILED", "Device-state request failed. Details suppressed."), cooldown: false };
  }
  if (!object(body) || !Array.isArray(body.deviceStates) || !Array.isArray(body.errors) ||
      !body.deviceStates.every(object) || !body.errors.every(object) ||
      ["message", "error", "errorCode", "errorType", "errorMessage"].some(key => body[key] != null)) {
    return { result: failure("INVALID_STATE_RESPONSE", "Amazon did not return the expected device-state response."), cooldown: false };
  }
  if (body.errors.length > 0) {
    return { result: failure("DEVICE_STATE_UNAVAILABLE", "Amazon reported one or more device-state errors; partial results are not treated as success."), cooldown: false };
  }
  if (body.deviceStates.length === 0) {
    return { result: failure("DEVICE_STATE_UNAVAILABLE", "Amazon returned no device states."), cooldown: false };
  }
  return { result: { content: [{ type: "text", text: JSON.stringify(body, null, 2) }] }, cooldown: false };
}

/** Process-local single-flight and cooldown. The library does not expose an
 * abort handle: a deadline bounds our response, not the underlying HTTP work.
 * Keep the slot occupied until the callback settles, even after a deadline.
 */
export function createDeviceStateQuery(
  { deadlineMs = DEFAULT_DEADLINE_MS, cooldownMs = DEFAULT_COOLDOWN_MS,
    now = Date.now } = {},
): (invoke: Invoke) => Promise<Result> {
  let inFlight = false;
  let nextAllowed = 0;
  const coolDown = () => { nextAllowed = Math.max(nextAllowed, now() + cooldownMs); };

  return (invoke) => {
    if (inFlight) return Promise.resolve(failure("STATE_QUERY_BUSY", "A previous device-state query is still outstanding. Do not retry immediately."));
    if (now() < nextAllowed) return Promise.resolve(failure("STATE_COOLDOWN", "Device-state queries are temporarily paused. Do not retry immediately."));

    inFlight = true;
    return new Promise<Result>(resolve => {
      let completed = false;
      let replied = false;
      const timer = setTimeout(() => {
        if (replied) return;
        replied = true;
        coolDown();
        resolve(failure("STATE_TIMEOUT", "Device-state query exceeded its response deadline. The upstream request may still be running; do not retry immediately."));
      }, deadlineMs);

      const finish = (error: unknown, body?: unknown) => {
        if (completed) return;
        completed = true;
        clearTimeout(timer);
        let outcome: ReturnType<typeof classify>;
        try {
          outcome = classify(error, body);
        } catch {
          outcome = { result: failure("INVALID_STATE_RESPONSE", "Device-state response could not be processed."), cooldown: false };
        }
        if (outcome.cooldown) coolDown();
        inFlight = false;
        if (!replied) {
          replied = true;
          resolve(outcome.result);
        }
      };

      try { invoke(finish); } catch (error) { finish(error); }
    });
  };
}
