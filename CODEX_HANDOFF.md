# Lapsrv: start here on zbook9

Updated November 13, 2026, ahead of the November 15 cyclocross race.

## Purpose and boundaries

Impinj4 distinguishes a remote early RFID reader connected through a WiFi bridge.
It sends those reads ONLY to lapsrv, giving officials advance notice of riders
approaching the finish. These are not finish reads and must not be forwarded to
CrossMgr. CrossMgr continues to receive its separate normal finish-reader stream.

Lapsrv obtains identity/category/lap context through read-only CrossMgr MCP.
Its allowlist is `bridge.identity`, `bridge.snapshot`, `instances.list`,
`race.roster`, and `race.review`. Do not add race mutations or provisional reads
as part of diagnosing this heads-up display.

## Installed laptop layout

- Git checkout and environment: `/home/sl/lapsrv`, `.venv` inside it.
- Branch: `develop`; origin: `git@github.com:stuartlynne/lapsrv.git`.
- Desktop: `~/Desktop/Lapsrv.desktop`; application menu: Lapsrv.
- Launcher: `~/.local/bin/lapsrv`; logs: `~/.local/state/lapsrv/application.log`.
- Settings: `~/.config/lapsrv/settings.json`.
- Remote settings administration token: `admin.token` beside settings.json.
- Default exports: `~/.local/share/lapsrv/exports`.
- Default JChip listener: TCP 53136; web UI: HTTP 8865.

The launcher uses this checkout's venv. Settings are independent of the separate
RaceVideo app and of the lapsrv instance on whiskey. Do not edit the old
`~/bin/lapsrv.py` thinking it is the installed desktop application.
Closing the Lapsrv Tk window stops this application, including its RFID listener;
this differs from RaceVideo's separate recorder lifecycle.

## Work completed in this session

1. Replaced active CrossMgr web/WebSocket scraping and required local XLSX input
   with the MCP adapter in `lapsrv_mcp.py`. Local workbook loading is no longer
   used by application startup; openpyxl remains for exports/legacy utilities.
2. Added a full registration `race.roster` endpoint to the separate crossmgr_mcp
   project. It reads CrossMgr's native linked workbook on the server and includes
   entrants before their first timing read, all tag columns and category context.
   Both currently tested laptop endpoints support it. A different/older server
   or gateway must expose that tool before lapsrv can use it.
3. Added named targets, current GUI/saved CMN modes, polling and operator options
   in Tk Settings and the web `/settings` page. Settings use atomic private JSON
   saves and revision checks. Target changes keep the receiver connection open.
4. Added a RaceVideo-style desktop installer, `tools/install_user.py`.
5. Diagnosed HTTP 401 failures: the zbook5 profile had inherited zbook9's token;
   at one point both profile URLs also pointed at zbook5. Corrected distinct host
   URLs and token-file references on both whiskey and zbook9. No tokens belong in
   this repository, handoff, logs or chat output.
6. Added explicit nested transport/authentication errors and a Tk status line
   showing selected target, endpoint and the error. A bare TaskGroup exception
   had previously hidden the HTTP 401 cause.

The main implementation commit is `1ff1ace`; this handoff follows it. Runtime
settings and token files are deliberately absent from Git.

## Connection state and event-day check

At the last check, both hosts had named zbook9 and zbook5 profiles, with zbook5
selected. Each uses its own token-file reference under `~/.config/racevideo/`:
`zbook9-crossmgr.token` or `zbook5-crossmgr.token`. They are client credentials;
do not replace either by copying the other host's token.

The whiskey instance connected to zbook5's current, unstarted Elite race with
15 participants and 15 EPC mappings. Its source CMN was under
`~/wimsey_crossmgr/sl/2026/Thrashers/BC_Championships/20261115-BCProvincialsCX2026/`.
The zbook9 client also successfully loaded that 15-rider roster. A separate saved
November 8 PartyCross Elite test against zbook9 loaded 29 participants/tags.
These are snapshots of test state: recheck the actual current race before use.

- Open Settings and choose the intended target; Save and apply.
- Use Current mode for the active CrossMgr GUI race. If several GUI instances
  exist, specify the intended instance ID or race path.
- Before the start, a populated roster with no race clock is expected.
- `RFID waiting` means no reader connection; it is independent of MCP readiness.
- Check Impinj4's dedicated early-reader destination and network reachability.
- HTTP 401 means that endpoint rejected its supplied bearer token. Check the
  selected profile's URL and token-file path on the machine running lapsrv.
- Use Refresh in web Settings to bypass cached roster/result analysis.
- Default polling is five seconds; unchanged analyses may be reused for a minute.

Do not silently use an old race when current discovery fails. New EPC matching
is disabled when MCP is unavailable/stale; there is no promised offline buffering
or backfill for unmatched early reads. Duplicate EPC assignments are omitted.
Changing races clears volatile observations; reconnect behavior also resets local
RFID runtime state. Restarting is not a mechanism for preserving a read history.

## Configuration and operation

Launch with `~/.local/bin/lapsrv` or its desktop icon. Web display is
`http://localhost:8865`; configure through Settings in either interface.
Local web administration uses localhost/127.0.0.1; remote administration needs
the operator token. Network listener/port changes, health hosts, Tk visibility
and export directory take effect next launch. Source/poll/group options apply
without restarting the receiver. Configuration edited directly on disk is not
automatically reloaded by a running app; use its Settings form or restart safely.

Race-host UTC start/finish values avoid mismatched workstation timezone databases
(Pacific timezone rules were an issue in this season's deployments). Configured
timezone/tzfile is only a fallback for naive source timestamps. Saved CMN paths
refer to the MCP host, while token and fallback tzfile paths refer to the client.

## Validation and limits

Run from this checkout:

```sh
.venv/bin/python -m unittest discover -s tests -q
```

All 16 tests passed on whiskey and zbook9 after the authentication/status changes.
They include a real local TCP JChip handshake/read and HTTP settings endpoint,
with simulated MCP responses. Browser/Tk smoke tests and installed launcher GUI
startup were also checked. Real MCP registration reads were verified as above.
No full live physical early-reader race operation has yet been validated.

Browser/Tk smoke commands and extra development dependencies are in README.md.
Do not invoke hardware readers or mutate live races simply to run unit tests.

## Git workflow and return of laptop changes

Whiskey checkout: `/home/sl/work26/sprinttimer/lapsrv`.
On zbook9, inspect and explicitly stage intended source changes, then commit:

```sh
cd ~/lapsrv
git status --short
git diff
git add path/to/changed-file.py CODEX_HANDOFF.md
git commit -m "Describe the fix and resulting behavior"
git push origin develop
```

If a network outage prevents pushing, local commits remain fetchable from whiskey.
Whiskey has a `zbook9` remote pointing at `sl@zbook9:/home/sl/lapsrv`:

```sh
cd /home/sl/work26/sprinttimer/lapsrv
git fetch zbook9
git log --oneline develop..zbook9/develop
git diff develop...zbook9/develop
git merge --ff-only zbook9/develop
git push origin develop
```

Alternatively, once laptop commits are pushed to GitHub, use `git pull --ff-only`
on whiskey. If histories diverge, review/merge deliberately; never force-reset
away edits. Keep notes about the concrete race observations and validation with
the code changes. Do not include tokens, race workbooks, result exports or logs.
The source checkout can be updated with `git pull --ff-only` while retaining its
ignored `.venv`; active processes load changed code only after a safe restart.
