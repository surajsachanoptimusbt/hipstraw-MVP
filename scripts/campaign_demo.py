"""Run the Hipstraw G0 campaign demo end to end, then open the campaign page.

    python scripts/campaign_demo.py             # both scenarios, then the page on http://127.0.0.1:8766/
    python scripts/campaign_demo.py --no-view   # build the database and the reports only

Both scenarios in docs/campaign_channel_scenarios.md (Kozmo on email only, then on email, LinkedIn and
Instagram) go through the same governed commands as docs/demo_g0_campaign_readiness.md: submit, L02 Strategy
validation (two gpt-4o calls), the review, L01 Readiness-first, the review again, and the report. The reviewer
and Sponsor decisions are scripted: the reviewer corrects "Same promise as the landing page" to not met where
the model judged otherwise (the landing page offers a selective 8-week cohort, the channels a free invoice
check) and accepts every other finding. Needs OPENAI_API_KEY in .env; a run costs a few cents.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SCENARIOS = [
    ("input/campaign/kozmo_email_us.yaml", "reports/demo_kozmo_email.md"),
    ("input/campaign/kozmo_three_channels_us.yaml", "reports/demo_kozmo_three_channels.md"),
]
REVIEWER, SPONSOR, CM = "Hipstraw Reviewer", "Kozmo GTM lead", "Hipstraw CM"
CORRECTION = ("The landing page offers an 8-week Genesis Cohort by selection ('Request a spot'), while this "
              "channel promises a free check of the last 90 days of invoices: two different offers.")
CLI = "from hipstraw_mm.cli import main; raise SystemExit(main())"


def hs(db: str, *args: str) -> dict[str, Any]:
    """One `hipstraw-mm campaign` command, its JSON result returned."""
    done = subprocess.run([sys.executable, "-c", CLI, "campaign", "--db", db, *args, "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit(f"campaign {' '.join(args[:2])} failed:\n{done.stderr.strip()[-1500:]}")
    result: dict[str, Any] = json.loads(done.stdout)
    return result


def decide(db: str, review_id: str) -> None:
    """The reviewer decides every finding and validates; the Sponsor accepts."""
    corrected = 0
    for f in hs(db, "review", "show", "--review", review_id)["findings"]:
        base = ["review", "finding", "--review", review_id, "--finding", f["findingId"], "--by", REVIEWER,
                "--as", "reviewer"]
        if f["kind"] == "rubric" and f["questionId"] == "CR04" and f["verdict"] != "not_met":
            hs(db, *base, "--correct", CORRECTION, "--verdict", "not_met",
               "--reason", "the pages make different offers")
            corrected += 1
        else:
            hs(db, *base, "--accept", "--reason", "checked against the evidence")
    hs(db, "review", "validate", "--review", review_id, "--by", REVIEWER, "--as", "reviewer")
    accepted = hs(db, "review", "accept", "--review", review_id, "--by", SPONSOR, "--as", "sponsor")
    print(f"    {review_id}: reviewed ({corrected} corrected), Position v{accepted['positionVersion']} accepted")


def run_scenario(db: str, launch_file: str, report: str) -> None:
    launch_id = hs(db, "submit", "--file", launch_file, "--by", SPONSOR, "--as", "sponsor")["runId"]
    print(f"\n{launch_file}\n  launch {launch_id}")
    for line, reason in (("L02", "core assumptions unverified"), ("L01", "Day Zero is near")):
        run_id = hs(db, "choose", "--launch", launch_id, "--line", line, "--reason", reason, "--by", CM, "--as",
                    "campaign_manager")["lineRunId"]
        ran = hs(db, "run", "--line-run", run_id, "--by", CM, "--as", "campaign_manager")
        for e in ran["executions"]:
            print(f"    {line} {e['moveId']}: {e['status']} ({e.get('note') or e['gate']})")
        decide(db, ran["reviewId"])
    hs(db, "report", "--launch", launch_id, "--out", report)
    print(f"  report: {report}")


def serve(db: str, port: int) -> None:
    page = subprocess.Popen([sys.executable, "-c", CLI, "campaign", "--db", db, "view", "--port", str(port)])
    for _ in range(50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.2)
    url = f"http://127.0.0.1:{port}/"
    print(f"\nCampaign page: {url}  (Report, Campaign and Reviewer desk; Ctrl+C stops it)")
    webbrowser.open(url)
    try:
        page.wait()
    except KeyboardInterrupt:
        page.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=".runs/campaign_demo_run.db", help="a new database, replaced on each run")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-view", action="store_true", help="do not start the page")
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("OPENAI_API_KEY", "").startswith("sk-") or "your-key" in os.environ["OPENAI_API_KEY"]:
        raise SystemExit("Put your OPENAI_API_KEY in .env (copy .env.example to .env first).")
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    try:
        db.unlink(missing_ok=True)
    except PermissionError:
        raise SystemExit(f"{db} is open in another program (a campaign page?); stop it and run again.") from None
    for launch_file, report in SCENARIOS:
        run_scenario(str(db), launch_file, report)
    if not args.no_view:
        serve(str(db), args.port)


if __name__ == "__main__":
    main()
