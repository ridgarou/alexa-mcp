/**
 * Interactive login flow.  Run:  npm run auth
 *
 * Starts the local proxy, shows the URL, and waits for the login. After a
 * successful login a smoke test (device list) runs and the token is stored in
 * .auth/alexa.json.
 */
import { defaultConfig, initAlexa } from "./alexa.js";
import { AUTH_PATH, hasAuth } from "./store.js";

async function main() {
  const cfg = defaultConfig();
  cfg.logger = () => {};

  // The URL we print MUST use proxyOwnIp — alexa-cookie2 builds its redirect
  // URLs with it, and proxyOwnIp must byte-match the browser URL. Default
  // 127.0.0.1 = log in on THIS machine.
  const displayIp = cfg.proxyOwnIp;

  const alreadyAuthed = hasAuth();

  console.error("");
  console.error("===============================================================");
  console.error(" alexa-mcp - login against " + cfg.amazonPage);
  console.error("===============================================================");
  if (alreadyAuthed) {
    console.error(` A token already exists (${AUTH_PATH}).`);
    console.error(" It will be loaded; a re-login is only needed once it expires.");
  } else {
    console.error(" No token present -> proxy login.");
    console.error("");
    console.error(" 1. Open in your browser (ideally on THIS machine):");
    console.error("");
    console.error(`       http://${displayIp}:${cfg.proxyPort}/`);
    console.error("");
    console.error(" 2. Sign in with your Amazon account (including 2FA).");
    console.error(" 3. The local proxy handles sensitive login traffic. Keep it private.");
    console.error(" For remote Docker hosts use an SSH tunnel, not a LAN-exposed proxy.");
    console.error("");
    console.error(" Waiting for login ... (abort with Ctrl+C)");
  }
  console.error("===============================================================");
  console.error("");

  const { alexa, fromStoredToken } = await initAlexa(cfg, /* interactive */ true);

  console.error(
    fromStoredToken
      ? "OK: token loaded from file - no login needed."
      : "OK: login successful - token saved.",
  );
  console.error(`OK: auth file: ${AUTH_PATH}`);

  // Smoke test: list devices.
  await new Promise<void>((res) => {
    alexa.getDevices((err: any, result: any) => {
      if (err) {
        console.error("FAILED: smoke test (getDevices). Details suppressed.");
      } else {
        const devices = result?.devices ?? [];
        console.error(`OK: smoke test - ${devices.length} devices`);
      }
      res();
    });
  });

  console.error("");
  console.error("Done. You can now start the server (npm start) or wire it up as an MCP.");
  process.exit(0);
}

main().catch(() => {
  console.error("ERROR: Authentication failed. Details suppressed.");
  process.exit(1);
});
