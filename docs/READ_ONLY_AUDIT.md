# Read-only audit

Source reviewed: fork src/index.ts and alexa-remote2 v8.1.1
(alexa-remote.js), with alexa-cookie2 v5.0.6 refresh implementation.
This is a static review, not an Amazon network trace or proof of server-side behavior.

| MCP tool | Library operation | Application purpose |
|---|---|---|
| alexa_list_devices | getDevices | GET registered devices |
| alexa_list_routines | getAutomationRoutines | GET automations |
| alexa_get_routine | getAutomationRoutines | GET automations, filter locally |
| alexa_list_scenes | getSmarthomeEntities | GET entities |
| alexa_get_activity | getCustomerHistoryRecords | GET CSRF page, POST history query |
| alexa_list_smarthome_devices | getSmarthomeDevices | POST GraphQL endpoint query, local mapping |
| alexa_audit_broken_references | getSmarthomeDevices, getSmarthomeEntities, getSmarthomeGroups, getAutomationRoutines | Same queries and local comparison |
| alexa_get_volumes | getAllDeviceVolumes | GET volume |
| alexa_get_do_not_disturb | getDoNotDisturb | GET status |
| alexa_query_device | querySmarthomeDevices | POST stateRequests; can contact devices to read state |
| alexa_list_groups | getSmarthomeGroups | GET groups |
| alexa_list_lists | getListsV2 | POST lists/fetch |
| alexa_get_list_items | getListItems / getListItemsV2 | POST items/fetch |
| alexa_get_player_info | getPlayerInfo | GET player state |
| alexa_list_notifications | getNotifications | GET notifications |

No device control, routine execution, deletion or update is called directly
by these handlers. POST alone does not indicate a write: GraphQL and state
queries use POST. The list ID is constrained and encoded before interpolation
in an upstream URL. Live state queries are bounded to 100 identifiers. RC.2 adds a process-local single-flight guard, a 25-second response deadline after authentication, a 15-second upstream request timeout and a 60-second cooldown after throttling or timeout. The upstream request is not cancelled by the deadline. Error responses are sanitized and returned with MCP isError; partial state results fail closed. No extra application retries are added.

The server's default read-only setting gates registration of write tools;
it is not an Amazon read-only credential. Initial authentication and token
refresh can use POST and other account operations, and local credential
persistence writes to disk. The upstream API is unofficial. Normal MCP
initialization now intercepts the upstream generateCookie fallback; tests
simulate a refresh failure without Amazon access. This guard depends on
the reviewed dependency implementation; changes require review and tests.

Device names, routine payloads, voice history, list items and notification
labels can contain private data or untrusted text. Never treat content
returned by Amazon as agent instructions. The read-only inventory is not a
complete skill inventory. Real integration and egress enforcement remain
pending. No credentials are required or permitted in CI.
