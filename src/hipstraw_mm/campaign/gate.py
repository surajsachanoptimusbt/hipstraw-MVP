"""Policy and authority gate (HA C7): role rights now; each Move's effect class with Unit 4. Fails closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hipstraw_mm.campaign.audit import record_audit
from hipstraw_mm.campaign.config import RolesConfig
from hipstraw_mm.campaign.models import Mandate
from hipstraw_mm.campaign.store import CampaignStore
from hipstraw_mm.errors import PreconditionError

if TYPE_CHECKING:
    from hipstraw_mm.campaign.repertoire import MoveDef
    from hipstraw_mm.market.trace import Tracer


def check_role(roles: RolesConfig, role: str, action: str) -> None:
    """Refuse an action the role does not hold. The caller audits both outcomes."""
    allowed = roles.roles.get(role)
    if allowed is None:
        raise PreconditionError(f"unknown role {role!r}; roles: {', '.join(sorted(roles.roles))}")
    if action not in allowed:
        raise PreconditionError(f"role {role!r} may not {action}; allowed: {', '.join(allowed)}")


def authorize(
    store: CampaignStore, roles: RolesConfig, *, launch_id: str | None, actor: str, role: str, action: str, at: str,
) -> None:
    """Check the role and audit a refusal before raising. An allowed action is audited by the caller,
    once it knows the before and after references."""
    try:
        check_role(roles, role, action)
    except PreconditionError as exc:
        record_audit(store, launch_id=launch_id, at=at, actor=actor, role=role, action=action, right=action,
                     outcome="refused", reason=str(exc))
        raise


# -- effect classes (Unit 4) -------------------------------------------------------------------------------


def check_move(move: MoveDef) -> tuple[bool, str]:
    """Whether a Move's effect classes may run in G0. A Move must pass every class it lists."""
    reasons: list[str] = []
    for effect in move.effectClasses:
        if effect == "E3":
            return False, "no approved Test Plan: G0 has no approval path for external effects (publish, send, spend)"
        if effect == "E0":
            reasons.append("E0 internal: policy gate passed")
        elif effect == "E1":
            reasons.append("E1 read: only sources named in the mandate")
        elif effect == "E2":
            if not move.promptVersion:
                return False, "E2 inference needs a declared, versioned prompt"
            reasons.append(f"E2 inference: declared Skill with prompt {move.promptVersion}; output is a proposal")
    return True, "; ".join(reasons)


def mandate_addresses(mandate: Mandate) -> list[str]:
    """The addresses a read Move may open: the product website and every asset address in the mandate."""
    urls = [a.url for a in mandate.assets if a.url]
    if mandate.product.website:
        urls.append(mandate.product.website)
    return list(dict.fromkeys(urls))


def check_read(url: str, mandate: Mandate) -> tuple[bool, str]:
    if url in mandate_addresses(mandate):
        return True, "named in the mandate"
    return False, f"{url} is not named in the mandate; reads are limited to mandate addresses"


def gate_move(tracer: Tracer, move: MoveDef) -> tuple[bool, str]:
    with tracer.step("authority_gate", "authority_gate", "check_authority", right="check_authority") as step:
        step.set_inputs({"moveId": move.id, "moveVersion": move.version, "effectClasses": list(move.effectClasses)})
        allowed, reason = check_move(move)
        step.add_check("effect_class", "pass" if allowed else "fail", reason)
        step.set_decision("allowed" if allowed else "refused", reason)
    return allowed, reason
