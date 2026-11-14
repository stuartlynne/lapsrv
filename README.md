# lapsrv

Early-reader heads-up display for race officials. Impinj4 sends the remote reader's
JChip stream to lapsrv; CrossMgr MCP supplies registration identities, categories,
lap information and race state. Early reads remain local to lapsrv. Its MCP client
only calls read tools and never submits passings or changes a CrossMgr race.

## Run

Requires Python 3.11+ and the platform Tk package (Ubuntu: `python3-tk`).

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python lapsrv.py
```

Install application-menu and desktop launchers, as with RaceVideo:

```sh
.venv/bin/python tools/install_user.py --desktop
```

The launcher uses this checkout's virtual environment and writes its log to
`~/.local/state/lapsrv/application.log`.

No workbook or command-line configuration is required. Open
<http://localhost:8865> for the approaching-rider display, and use **Settings**
(or the Tk **Settings…** button). For web-only operation:

```sh
.venv/bin/python lapsrv.py --no-gui
```

The default JChip receiver is TCP port **53136**, and web port is **8865**.
Configure Impinj4's dedicated early-reader destination accordingly. Ensure the
listener is reachable from the WiFi bridge. This is independent of CrossMgr's
finish-reader destination.

## CrossMgr connections

Settings supports named MCP targets. Select an existing target or enter a new
name in **Save current target as**, edit its connection and **Save and apply**.
The selected target and all profiles persist across runs. On first use, profiles
are copied from `~/.config/racevideo/crossmgr.json` if present; the applications'
settings are independent thereafter. `RACEVIDEO_CROSSMGR_CONFIG` overrides the
import location.

* **Current** follows the active CrossMgr GUI race on the selected MCP host.
  If there are multiple GUIs, provide its instance ID or current race path.
* **Saved** uses an explicit CMN path **on the MCP server host**. It is labelled
  as a saved source; it is never silently substituted for an unavailable live race.
* **Refresh current race now** forces a fresh snapshot and registration/results
  refresh, including linked-workbook edits.
* Authentication uses a **token-file path on the lapsrv host**. Token contents
  are not stored in settings or sent to the browser.
* Gateway tool-name aliases are editable under advanced web settings. Required
  canonical names are `bridge.identity`, `bridge.snapshot`, `race.roster` and
  `race.review`.

The MCP server must include the new read-only **`race.roster`** endpoint. It
provides the full native linked-workbook roster, including entrants who have no
finish reads, all tag columns and category memberships. The workbook stays with
CrossMgr; lapsrv does not need an XLSX copy. This endpoint is installed on zbook9;
other servers/gateways must be updated before selecting them.

An unavailable or stale MCP source disables new EPC-to-rider matching and shows
an explicit status. Existing observations are retained while reconnecting to the
same race; switching races clears the in-memory approaching-rider history.
Duplicate EPC assignments are omitted rather than choosing an arbitrary rider.
The default poll is five seconds. Unchanged snapshot analyses are cached for up
to a minute; explicit refresh bypasses the cache. Source-host UTC start/finish
values prevent differences in workstation timezone databases from shifting race
time. Configured timezone/tzfile is a fallback for older naive timestamps.

## Saved configuration

Settings live at `~/.config/lapsrv/settings.json`, or `--config PATH` /
`LAPSRV_CONFIG`. Saves are atomic and private; conflicting edits require reload.
Tk window geometry is retained.

Source selection, polling, grouping and unknown-tag options apply while running.
Receiver/web bind addresses and ports, health-check hosts, Tk visibility and
export directory are saved for the next launch. The web form reports restart
requirements; saving settings does not disconnect the reader.

Local settings access uses `localhost` or `127.0.0.1`. To administer from another
computer, enter the operator token from `admin.token` beside the settings file.
The public approaching-rider page needs no token. Use a trusted race network or
HTTPS proxy for remote administration; HTTP itself does not encrypt traffic.

Each target needs its own correct bearer-token file. A zbook9 token is not
necessarily valid on zbook5. Configuration is local to each computer: fixing the
laptop's settings does not update an already-running whiskey instance. The Tk
window shows the selected target, endpoint and specific connection error; HTTP
401 means the selected server rejected the supplied credentials.

Existing automation can still use CLI flags (`--help`). Overrides affect that run
unless `--save-config` is supplied; pressing Save in Settings also persists the
current form. `--xlsx` and the old web-scraping `--crossmgr` option now report a
migration error. CSV/XLSX exports remain available under
`~/.local/share/lapsrv/exports`, separated by source race identity.

## Validation

```sh
python -m unittest discover -s tests -q
PYTHONPATH=. xvfb-run -a python tests/tk_smoke.py
PYTHONPATH=.:tests python tests/browser_smoke.py
```

The browser smoke requires Chrome, `websockets` and Pillow; the Tk smoke requires
Pillow and Xvfb. Screenshots are written under `artifacts/`. Unit/integration tests
exercise the actual TCP JChip handshake and HTTP settings server, with simulated
MCP responses. A real zbook9 saved Elite race also returned 29 named/tagged
entrants. Current-GUI behavior is simulated in tests; a physical early reader and
an active race still need event-side validation.

`README-lapsrv.md` contains the historical design, including earlier workbook and
WebSocket instructions superseded by this file.
