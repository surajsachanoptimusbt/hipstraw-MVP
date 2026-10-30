"""Mechanism stamp (HA C8; research R13): the versions of everything that produced a Review or snapshot."""

from __future__ import annotations

import subprocess
from functools import cache
from importlib.metadata import PackageNotFoundError, version

from hipstraw_mm.campaign.models import MechanismStamp, ModelUse


@cache
def _code_version() -> str:
    try:
        return version("hipstraw-mm")
    except PackageNotFoundError:
        return "unknown"


@cache
def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def mechanism_stamp(
    *,
    repertoire_version: str | None = None,
    criteria_version: str | None = None,
    rubric_version: str | None = None,
    prompt_versions: list[str] | None = None,
    models: list[ModelUse] | None = None,
    router_version: str | None = None,
) -> MechanismStamp:
    return MechanismStamp(
        codeVersion=_code_version(), gitCommit=_git_commit(), repertoireVersion=repertoire_version,
        criteriaVersion=criteria_version, rubricVersion=rubric_version, routerVersion=router_version,
        promptVersions=sorted(set(prompt_versions or [])), models=models or [],
    )
