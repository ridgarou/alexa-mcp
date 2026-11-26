import {
  closeSync, constants, fstatSync, fsyncSync, mkdirSync, mkdtempSync,
  openSync, readFileSync, renameSync, rmSync, writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";

/**
 * Store registration data verbatim; it contains long-lived credentials.
 * The deployment must keep the directory private and prevent concurrent
 * authentication sessions. Atomic replacement avoids partially written JSON.
 */
export const AUTH_PATH = resolve(process.env.ALEXA_MCP_AUTH_PATH ?? ".auth/alexa.json");

export type CookieData = Record<string, unknown>;

function isCookieData(data: unknown): data is CookieData {
  return !!data && typeof data === "object" && !Array.isArray(data)
    && Object.keys(data).length > 0;
}

export function loadAuth(path: string = AUTH_PATH): CookieData | undefined {
  let fd: number | undefined;
  try {
    fd = openSync(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0)
      | (constants.O_NONBLOCK ?? 0));
    if (!fstatSync(fd).isFile()) throw new Error("Not a regular file");
    const data: unknown = JSON.parse(readFileSync(fd, "utf8"));
    if (!isCookieData(data)) throw new Error("Invalid authentication data");
    return data;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") {
      console.error("[store] Could not read authentication data. Details suppressed.");
    }
    return undefined;
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
}

export function saveAuth(data: CookieData, path: string = AUTH_PATH): void {
  let temporaryDir: string | undefined;
  let fd: number | undefined;
  try {
    if (!isCookieData(data)) throw new Error("Invalid authentication data");
    const serialized = JSON.stringify(data, null, 2);
    const dir = dirname(path);
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    // Same filesystem as the destination: rename is an atomic replacement.
    temporaryDir = mkdtempSync(join(dir, ".alexa-auth-"));
    const temporaryFile = join(temporaryDir, "token");
    fd = openSync(temporaryFile, "wx", 0o600);
    writeFileSync(fd, serialized, "utf8");
    fsyncSync(fd);
    closeSync(fd);
    fd = undefined;
    renameSync(temporaryFile, path);
  } catch {
    throw new Error("Unable to persist Alexa authentication data. Details suppressed.");
  } finally {
    if (fd !== undefined) closeSync(fd);
    if (temporaryDir !== undefined) rmSync(temporaryDir, { recursive: true, force: true });
  }
}

export function hasAuth(path: string = AUTH_PATH): boolean {
  return loadAuth(path) !== undefined;
}
