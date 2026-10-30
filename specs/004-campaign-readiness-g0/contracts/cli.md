# CLI Contract: `hipstraw-mm campaign`

All commands accept the global `--json` and `--config-dir DIR` (default `config`) and the group option
`--db PATH` (default `$HIPSTRAW_CAMPAIGN_DB`, else `.runs/campaign.db`). The campaign group does not
build the market context, so no Firestore, search key or market program is needed.

Actions that change state take `--by NAME --as ROLE`. Roles and their actions are in
`config/campaign/roles.yaml` (contracts/config.md). A role that lacks the action is refused with exit
code 2, and the refusal is audited.

Exit codes (as in the rest of the CLI): `0` ok; `1` usage, config or validation error (for example a
launch file that fails its schema, a repertoire that fails the Line lint); `2` precondition or state
error (wrong lifecycle state, stale commit, role not allowed, unknown ID); `3` external service error
(model or page read failed after retries); `4` model-call budget exhausted. Errors go to stderr as
`error: <message>`; with `--json`, stdout carries `{"command", "error": {"code", "message"}}`.

| Command | Purpose | Key output (`--json`) |
|---|---|---|
| `campaign lint` | Load the repertoire, criteria, layers and roles; run the Line lint | `repertoireVersion`, `moves`, `lines`, `errors[]` |
| `campaign submit --file F --by N --as R` | Launch intake: mandate v1, evidence, proposed Position v1 (US1) | `launchId`, `mandateVersion`, `evidence`, `positionVersion`, `items` by kind |
| `campaign amend --launch L --file F --by N --as sponsor` | New mandate version; new assets become evidence | `mandateVersion`, `evidence` |
| `campaign show --launch L` | Launch status: mandate version, head Position, Line runs, Reviews | full summary |
| `campaign lines --launch L` | Line recommendation from the head Position (US2) | `facts`, `eligible[]`, `excluded[]` |
| `campaign choose --launch L --line ID --reason T --by N --as campaign_manager` | Open the tactic record | `lineRunId`, `lineId`, `lineVersion` |
| `campaign deviate --line-run R (--skip M \| --add M [--stage K]) --reason T --by N --as campaign_manager` | Record a deviation that applies before the next stage | `deviationId`, `plannedStages` |
| `campaign step --line-run R --by N --as campaign_manager` | Run the next stage; after the last stage, draft the Review | `stage`, `executions[]`, `reviewId?` |
| `campaign run --line-run R --by N --as campaign_manager` | Run all remaining stages, then draft the Review | `executions[]`, `reviewId` |
| `campaign stop --line-run R --reason T --by N --as campaign_manager` | Abandon the Line; draft the Review on what ran | `state: abandoned`, `reviewId` |
| `campaign review show --review V` | Review, findings, corrections, proposed successor | full Review |
| `campaign review finding --review V --finding F (--accept \| --reject \| --correct TEXT) --reason T --by N --as reviewer` | Review queue action on one finding (US4) | `findingId`, `reviewState` |
| `campaign review validate --review V --by N --as reviewer` | `drafted → validated`; refused while any finding is pending | `state` |
| `campaign review accept --review V --by N --as sponsor [--reason T]` | `validated → accepted`; commits the successor Position or refuses as stale | `state`, `positionVersion` |
| `campaign review reject --review V --reason T --by N --as sponsor` | `validated → rejected` | `state` |
| `campaign report --launch L [--out PATH]` | Render the report from the head accepted Position (US5); refused if none is accepted | `reportId`, `path`, `sha256` |
| `campaign measures [--from DATE] [--to DATE]` | G0 → G1 measures from stored records (US6) | each measure with the record IDs it counted |

Without `--json`, commands print a short human summary. `lines`, `show` and `review show` print tables
that a reviewer can work from without the database (SC-006).
