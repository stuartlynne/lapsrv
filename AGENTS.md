# Lapsrv session entry point

Read `CODEX_HANDOFF.md` first, then `README.md` for current startup/configuration.
The historical `README-lapsrv.md` describes older workbook/WebSocket behavior.

Keep early RFID observations local to lapsrv: the CrossMgr MCP client is read-only.
Preserve machine-local settings, tokens, environments and race exports. Check
active listeners/readers before restarting an operator's app. Make focused source
commits on `develop` so laptop changes can be fetched back after the race.
