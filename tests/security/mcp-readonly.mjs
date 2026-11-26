import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const expected = [
  "alexa_list_devices", "alexa_list_routines", "alexa_get_routine",
  "alexa_list_scenes", "alexa_get_activity", "alexa_list_smarthome_devices",
  "alexa_audit_broken_references", "alexa_get_volumes", "alexa_get_do_not_disturb",
  "alexa_query_device", "alexa_list_groups", "alexa_list_lists",
  "alexa_get_list_items", "alexa_get_player_info", "alexa_list_notifications"
].sort();
const client = new Client({ name: "offline-security-test", version: "1.0.0" });
const transport = new StdioClientTransport({
  command: process.execPath,
  args: ["dist/index.js"],
  env: {
    ALEXA_MCP_ALLOW_WRITE: "0",
    ALEXA_MCP_AUTH_PATH: "/nonexistent-alexa-test-directory/alexa.json",
    ALEXA_MCP_PROXY_BIND: "127.0.0.1"
  },
  stderr: "ignore"
});
try {
  await client.connect(transport);
  const { tools } = await client.listTools();
  assert.deepEqual(tools.map(t => t.name).sort(), expected);
  for (const tool of tools) assert.equal(tool.inputSchema.type, "object");
  const routine = tools.find(t => t.name === "alexa_list_routines");
  assert.ok(routine.inputSchema.properties.limit);
  let rejected = false;
  try {
    const r = await client.callTool({ name: routine.name, arguments: { limit: "invalid" } });
    rejected = r.isError === true && /invalid|validation|expected|number/i.test(JSON.stringify(r.content)) && !/No Alexa auth/i.test(JSON.stringify(r.content));
  } catch (e) {
    rejected = e.code === -32602 || /invalid|validation|expected|number/i.test(e.message);
  }
  assert.ok(rejected, "Invalid argument must be rejected before auth");
  const r = await client.callTool({ name: "alexa_list_devices", arguments: {} });
  assert.equal(r.isError, true);
  assert.match(JSON.stringify(r.content), /No Alexa auth/);
  console.log("PASS: exact 15-tool inventory, schemas, invalid input, missing auth");
} finally {
  await client.close();
}
