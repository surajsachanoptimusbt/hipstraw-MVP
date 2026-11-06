# Hipstraw web app: reviewer desk and customer workspace (MVP)

6 Nov 2026. Responds to the 6 Nov meeting:
- predefined Lines and Moves, picked by playbook rules, not by a model;
- a reviewer desk that shows each request and what the agent is doing (the Lines picked, the Lines available, the
  evidence), with the actions a person takes;
- a customer workspace for Hipstraw's three offerings: shadow launch, Day Zero launch and campaign management.

## Run it

```
.venv\Scripts\python scripts\start_hipstraw.py
```

The script starts the desk API and the web app, then opens the reviewer desk.

| What | Where |
|---|---|
| Reviewer desk | http://127.0.0.1:3000/desk |
| Customer workspace | http://127.0.0.1:3000/workspace |
| Desk API, with its docs | http://127.0.0.1:8000/docs |

Options:
- `--fresh`: start from an empty desk; the sample requests are opened again.
- `--dev`: run the web app with hot reload.

Ctrl+C stops both.

Needs Node.js. The first start installs the web app's packages and builds it. No model and no API key are used.

## Architecture

The pipeline follows the architecture reviewed on 6 Nov:

| Stage | Who | What it does |
|---|---|---|
| 1 Ingest | agent | Reads the request: product, market, thesis, hypotheses, evidence |
| 2 Review | agent | Places the evidence on the ladder and judges it against the demand rubric |
| 3 Position | agent | Sets where each hypothesis stands: the rubric decision |
| 4 Recommend | playbook | For each task, checks the available Lines' conditions, ranks the eligible ones in playbook order, picks the first. Jev is deferred (constitution XI). |
| 5 Workflow | agent | Lays out each Line's Moves in order. The Moves that contact people, publish or spend wait for approval. |
| 6 Human approval | reviewer | Approves the plan, bound to its payload hash, or returns it with a note |

**State and audit ledger:** one SQLite file, `.runs/desk.db`.
- Every step is one SQL transaction: it appends the step's events to the ledger and updates the case.
- The ledger is append-only: database triggers refuse any update or delete.
- Each entry carries the hash of the one before it. `hipstraw-mm desk verify`, and the Ledger page, recompute the
  chain.

**Pacing:** the agent waits 0.6 s between steps, so a person can follow it live. This changes nothing else.

**Code:**

| Part | Where |
|---|---|
| Web app (Next.js 16, React 19, Tailwind 4, Motion) | `web/` |
| Desk API (FastAPI) | `src/hipstraw_mm/desk/api.py` |
| Desk operations, shared by the CLI and the API | `src/hipstraw_mm/desk/service.py` |
| Agent | `src/hipstraw_mm/desk/agent.py` |
| Store and ledger | `src/hipstraw_mm/desk/store.py` |
| Playbook | `src/hipstraw_mm/foundry/playbook.py` |

## Approved actions (constitution XIII)

The web app is a governed console:
- It changes state only through the desk's operations, the same ones the CLI calls (`hipstraw-mm desk ...`).
- Every change names the acting person and role.
- An authority gate checks the role and fails closed. The roles are in `config/desk/roles.yaml`.

| Action | Who | Where | Effect |
|---|---|---|---|
| Submit a market validation request | customer, reviewer | Customer workspace, New request | Opens a case; the agent works it |
| Approve the plan | reviewer | Reviewer desk, the case | The case is approved. Refused if the plan changed since it was shown. |
| Return the plan | reviewer | Reviewer desk, the case | The case goes back to the customer; a note is required |

There is no sign-in in this MVP. The desk acts as "Hipstraw reviewer" and the workspace as the customer's team.

## What is live and what is a preview

| Offering | State | What exists |
|---|---|---|
| Shadow launch: market validation | Live | Requests, the agent's run, Lines and Moves, metrics, findings, evidence, approval, ledger |
| Day Zero launch | Preview | A timeline from T-30 to T+30, on a sample plan, labelled as such |
| Campaign management | Preview | Channel findings on sample data, labelled as such. Campaign reviews run today in the CLI (`hipstraw-mm campaign`). |

## Next

- Connect the campaign module's launches to the desk as their own case type: campaign review, with its Lines L01 to
  L05.
- Day Zero launch as a live case type: T-30 activities, launch day, post-launch.
- Record evidence as the Moves run, so the metrics and findings move.
- Sign-in, and each customer seeing only its own requests.
