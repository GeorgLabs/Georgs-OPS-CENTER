# OPS//CENTER

A server-monitoring dashboard. The frontend is finished and waiting. **The backend is yours to build.**

Right now every endpoint answers `501 Not Implemented`. Your job: make the dashboard come alive,
one milestone at a time, with FastAPI + Pydantic + SQLModel - the same stack real companies run.

No points, no attempts, no timers. The only judge is the running code.

## Start

**Windows:** double-click `setup.bat` (once), then `run.bat`.
**Linux/Mac:** `./setup.sh` (once), then `./run.sh`.

The browser opens at <http://127.0.0.1:8000>. Open the folder in VS Code (`code .`) and keep the
page next to it. The server restarts by itself whenever you save a `.py` file.

## How you know what to do

Open **Mission Control** (first page). It runs ~40 probes against *your* code, live:

| mark | meaning |
|---|---|
| `...` todo | the endpoint still answers 501 - not built yet, nothing wrong |
| `X` fails | it answers, but not what the contract says - the message tells you exactly what it got |
| `OK` | works |

The probes are plain Python in `app/dev/probes.py`. **Read them** - they are the spec, and reading
them is allowed and encouraged. Each stub function also has its spec in its docstring.
Nothing is stored anywhere; the page just asks "does it work right now?".

## The route

| | milestone | you edit | you will use |
|---|---|---|---|
| **M1** | Hello, data | `app/routers/system.py` | FastAPI routes, Pydantic models, query parameters, `psutil` |
| **M2** | Hosts & database | `app/routers/hosts.py`, `ingest.py` | SQLModel, sessions, pagination, API keys |
| **M3** | Who are you? | `app/security.py`, `app/routers/auth.py` | Argon2 password hashing, JWT, dependencies |
| **M4** | Red team | `app/ratelimit.py`, `app/middleware.py`, + your whole API | think like an attacker |
| **M5** | Ship it | `tests/test_yours.py` | pytest, then the real codebase |

M4 is different: those probes are **attacks**. `blocked` is good, `BREACHED` means the attack worked
against you. Some holes are in your own code from M2/M3 - the point is to find them (and why they happen).

## Your toolbox

- **Traffic** page - every request your API gets, live, with bodies. Passwords are masked on purpose.
- **API docs** (`/docs`) - interactive Swagger UI generated from your code. Try endpoints with the *Authorize* button.
- **Agent** - once M2 works: create a host in the UI, copy the command it shows, run it in a second terminal.
  Your own computer starts reporting CPU/memory/disk and the charts move.
- `ruff check .` (style + security lint) and `python -m pytest` - run them from the `.venv`
  (`.venv\Scripts\python -m ruff check .` on Windows).

## Rules of the game

1. You can't break anything. The database is a file; delete `opscenter.db` for a fresh start.
2. Use any help you like - docs, AI, Stack Overflow - but **be able to explain every line you keep.**
   In M4 you'll see exactly what copy-pasted code tends to forget.
3. Never share or commit `.env` (it holds your secret key).
4. Break your own app on purpose. That's the real game.

## Side quests (when you're ahead)

- Write an attack script (`requests`/`httpx2`) that tries to get into someone else's host.
- Make `/api/hosts` return `ETag`s, or add a `PATCH` endpoint to rename a host.
- Add an alert: if a host is above 90 % CPU, flag it in the response.
- Run the agent on a Linux box of yours and watch it show up in the dashboard.
