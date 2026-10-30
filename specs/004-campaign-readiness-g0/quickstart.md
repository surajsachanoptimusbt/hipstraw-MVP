# Quickstart: validate Hipstraw G0 end to end

This guide proves the feature works. Command details are in [contracts/cli.md](contracts/cli.md), file
formats in [contracts/config.md](contracts/config.md), and records in [data-model.md](data-model.md).

## Prerequisites

- The project's virtual environment with `pip install -e ".[dev]"`. On machines where Application
  Control blocks `hipstraw-mm.exe`, run the CLI as
  `python -c "from hipstraw_mm.cli import main; raise SystemExit(main())" ...`.
- `OPENAI_API_KEY` in `.env` only for the live L02 run in step 5; everything else makes no model call.
- A scratch database: `set HIPSTRAW_CAMPAIGN_DB=.runs/campaign-quickstart.db` (PowerShell:
  `$env:HIPSTRAW_CAMPAIGN_DB=...`).

## 1. Repertoire check

`hipstraw-mm campaign lint` → exit 0, `campaign-repertoire.v0.1`, 12 Moves, 5 Lines, no errors.
Change one Line's stage to name `M99` in a copy of the config and run with `--config-dir` on the copy →
exit 1, error naming the Line and `M99`.

## 2. Launch intake (US1)

`hipstraw-mm campaign submit --file input/campaign/example_launch.yaml --by "Demo Sponsor" --as sponsor`
→ a `launchId`, mandate v1, one evidence record per asset (`reported`), Position v1 `proposed` with
claims, three or more open core assumptions, and an unknown for each missing required input.

## 3. Line choice (US2)

`hipstraw-mm campaign lines --launch <launchId>` → with Day Zero 10 days away and no metrics: L01 and
L02 eligible with reasons; L04 excluded ("campaign not live"); L03 excluded ("no authorized test
channel").

`hipstraw-mm campaign choose --launch <launchId> --line L01 --reason "Day Zero in 10 days" --by "Demo CM" --as campaign_manager`
→ a `lineRunId`.

## 4. Run L01 with one deviation (US3)

1. `campaign step --line-run <id> ...` → stage 1 runs M01.
2. `campaign deviate --line-run <id> --skip M05 --reason "dates confirmed by phone" ...`
3. `campaign run --line-run <id> ...` → M04 runs, M05 is skipped, M12 escalates open blockers; a Review
   is `drafted`.

Check: `campaign show --launch <launchId>` lists the deviation; no model call appears in the trace.

## 5. Run L02 with recorded model responses (US3, E2)

With `HIPSTRAW_REPLAY=replay` and `HIPSTRAW_REPLAY_DIR=tests/fixtures/campaign/recorded`, choose and run
L02 on the same launch. Check: M06 and M07 outputs are proposals with evidence references; no claim is
above `reported`; each model call is a traced `call_model` step with prompt, response and cost.

## 6. Review queue and acceptance (US4)

1. `campaign review show --review <reviewId>` → findings `F01...`, each `pending`.
2. Correct one finding and reject one with `campaign review finding ... --as reviewer`; accept the rest.
3. `campaign review validate --review <reviewId> --by "Demo Reviewer" --as reviewer`.
4. `campaign review accept --review <reviewId> --by "Demo Sponsor" --as sponsor` → Position v2 `accepted`.
5. Accept a second Review that pinned v1 → exit 2, "stale: base v1 is no longer the head (v2)".

## 7. Report (US5)

`hipstraw-mm campaign report --launch <launchId> --out reports/<launchId>_readiness.md` → the report
opens with the scope statement; every finding cites evidence or is labelled assumption or unknown; no
score, probability or forecast appears.

## 8. Measures (US6)

`hipstraw-mm campaign measures --json` → Reviews completed, correction and rejection rates, blockers
before versus after Day Zero, Line usage, deviations per stage (one `skipped` at L01 stage 2), cost and
time per Review, each with the record IDs counted.

## Automated equivalent

`python -m pytest tests -q -k campaign` runs every step above on `:memory:` with fake or replayed model
calls; `ruff check src tests` and `mypy src` stay clean.
