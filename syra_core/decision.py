"""PPC-00B -- canonical authority resolution.

Discovery answers *where does this appear to exist*. This gate answers the
question that actually unblocks work: *for each capability, what should we do
about it?*

    REUSE          one authority, tested. Plug it into the core as-is.
    HARDEN         one authority, untested or uncontracted. Keep it, add proof.
    ADAPT          exists and works, but does not speak the core's contracts.
                   Wrap it. Do not rewrite it.
    CONSOLIDATE    several authorities claim it. Pick one, retire the rest.
                   This is the root cause of panels that break on integration.
    BUILD          no canonical implementation. Build it on the core.
    DO_NOT_TOUCH   critical runtime, currently working. Freeze until there is
                   runtime evidence. Refactoring this on grep output is how a
                   working system gets broken by its own cleanup.
    CORE_PROVIDED  the core already implements it. Stop maintaining a copy.

Two honesty rules are enforced structurally rather than by discipline:

1. Every decision carries a ``confidence`` and the signals that produced it.
   Static analysis cannot see reachability or deployment, so nothing here is
   ever certified -- it is a ranked, reviewable proposal.
2. ``implementationAuthorized`` is always false. This gate decides *what*, never
   *when*, and never applies anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import util
from .capabilities import (
    CAPABILITY_COUNT,
    CORE_PROVIDED,
    FRAGILITY_CRITICAL_RUNTIME,
    get as get_capability,
)
from .evidence import EvidenceRun
from .safety import SafetyContract
from .scanner import (
    MULTI_REPOSITORY,
    NO_CANONICAL_SOURCE,
    SINGLE_REPOSITORY,
    CapabilitySummary,
    ScanResult,
)

GATE = "PPC-00B-CANONICAL-AUTHORITY-RESOLUTION"
WORK_ID = "SYRA-PRODUCT-PLATFORM-001"

REUSE = "REUSE"
HARDEN = "HARDEN"
ADAPT = "ADAPT"
CONSOLIDATE = "CONSOLIDATE"
BUILD = "BUILD"
DO_NOT_TOUCH = "DO_NOT_TOUCH"
CORE_PROVIDED_MODE = "CORE_PROVIDED"

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

#: Lower runs first. Drives the recommended order of work.
_PRIORITY = {
    CONSOLIDATE: 1,
    BUILD: 2,
    HARDEN: 3,
    ADAPT: 4,
    CORE_PROVIDED_MODE: 5,
    REUSE: 6,
    DO_NOT_TOUCH: 7,
}


@dataclass
class Decision:
    """What to do about one capability, and why."""

    capability: str
    layer: str
    fragility: str
    mode: str
    confidence: str
    rationale: str
    action: str
    repositories: int
    source_candidates: int
    test_candidates: int
    contract_candidates: int
    repos: Tuple[str, ...] = ()
    signals: Tuple[str, ...] = ()

    @property
    def priority(self) -> int:
        return _PRIORITY.get(self.mode, 99)

    def as_row(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "layer": self.layer,
            "fragility": self.fragility,
            "mode": self.mode,
            "confidence": self.confidence,
            "repositories": self.repositories,
            "source_candidates": self.source_candidates,
            "test_candidates": self.test_candidates,
            "rationale": self.rationale,
            "action": self.action,
        }

    def as_dict(self) -> Dict[str, Any]:
        payload = self.as_row()
        payload["repos"] = list(self.repos)
        payload["signals"] = list(self.signals)
        return payload

    def render(self) -> str:
        return "CAPABILITY={}|MODE={}|CONFIDENCE={}|REPOS={}|RATIONALE={}".format(
            self.capability,
            self.mode,
            self.confidence,
            self.repositories,
            util.truncate(self.rationale, 90),
        )


def decide_one(summary: CapabilitySummary) -> Decision:
    """Apply the decision table to one capability summary.

    Deterministic and total: the same summary always yields the same decision,
    and every capability gets one. A decision table you can read in full is
    reviewable; a heuristic scattered across call sites is not.
    """
    capability = get_capability(summary.capability)
    signals: List[str] = []

    tested = summary.test_candidates > 0
    contracted = summary.contract_candidates > 0
    critical = summary.fragility == FRAGILITY_CRITICAL_RUNTIME
    core_provides = summary.capability in CORE_PROVIDED

    if tested:
        signals.append("HAS_TEST_EVIDENCE")
    else:
        signals.append("NO_TEST_EVIDENCE")
    if contracted:
        signals.append("HAS_CONTRACT_SIGNAL")
    if critical:
        signals.append("CRITICAL_RUNTIME")
    if core_provides:
        signals.append("CORE_IMPLEMENTS_THIS")
    if summary.noncanonical_evidence > summary.source_candidates:
        signals.append("MOSTLY_HISTORICAL_EVIDENCE")

    # --- no implementation found -------------------------------------
    if summary.status == NO_CANONICAL_SOURCE:
        if core_provides:
            return Decision(
                capability=summary.capability,
                layer=summary.layer,
                fragility=summary.fragility,
                mode=CORE_PROVIDED_MODE,
                confidence=HIGH,
                rationale=(
                    "No implementation in the workspace, and syra_core already "
                    "ships this capability."
                ),
                action=(
                    "Consume it from syra_core via ProductRuntime. Do not build "
                    "a second implementation."
                ),
                repositories=0,
                source_candidates=summary.source_candidates,
                test_candidates=summary.test_candidates,
                contract_candidates=summary.contract_candidates,
                signals=tuple(signals),
            )
        return Decision(
            capability=summary.capability,
            layer=summary.layer,
            fragility=summary.fragility,
            mode=BUILD,
            confidence=HIGH if summary.noncanonical_evidence == 0 else MEDIUM,
            rationale=(
                "No canonical source implementation found"
                + (
                    " ({} historical matches exist and may be worth reading "
                    "first).".format(summary.noncanonical_evidence)
                    if summary.noncanonical_evidence
                    else "."
                )
            ),
            action=(
                "Build it on top of the core's seams: {}".format(capability.intent)
            ),
            repositories=0,
            source_candidates=summary.source_candidates,
            test_candidates=summary.test_candidates,
            contract_candidates=summary.contract_candidates,
            signals=tuple(signals),
        )

    # --- several authorities claim it --------------------------------
    if summary.status == MULTI_REPOSITORY:
        if critical:
            # Consolidating a critical runtime capability from static evidence
            # is the highest-variance move available. Name the conflict, then
            # demand runtime proof before anyone touches it.
            return Decision(
                capability=summary.capability,
                layer=summary.layer,
                fragility=summary.fragility,
                mode=CONSOLIDATE,
                confidence=LOW,
                rationale=(
                    "{} repositories implement a CRITICAL_RUNTIME capability. "
                    "Static evidence cannot tell which one production actually "
                    "uses.".format(summary.repositories)
                ),
                action=(
                    "Do not refactor yet. First establish which implementation "
                    "is reachable from the deployed entrypoint (runtime trace "
                    "or import graph), then consolidate onto it and retire the "
                    "others behind the core's contracts."
                ),
                repositories=summary.repositories,
                source_candidates=summary.source_candidates,
                test_candidates=summary.test_candidates,
                contract_candidates=summary.contract_candidates,
                repos=summary.repos,
                signals=tuple(signals),
            )
        return Decision(
            capability=summary.capability,
            layer=summary.layer,
            fragility=summary.fragility,
            mode=CONSOLIDATE,
            confidence=MEDIUM,
            rationale=(
                "{} repositories carry an implementation. Divergent copies are "
                "the direct cause of integrations that break at the "
                "boundary.".format(summary.repositories)
            ),
            action=(
                "Pick the authority with test coverage and live consumers; move "
                "the others to it behind a core contract; delete the losers "
                "rather than leaving them to drift."
            ),
            repositories=summary.repositories,
            source_candidates=summary.source_candidates,
            test_candidates=summary.test_candidates,
            contract_candidates=summary.contract_candidates,
            repos=summary.repos,
            signals=tuple(signals),
        )

    # --- exactly one authority ---------------------------------------
    if summary.status == SINGLE_REPOSITORY:
        if critical and tested:
            return Decision(
                capability=summary.capability,
                layer=summary.layer,
                fragility=summary.fragility,
                mode=DO_NOT_TOUCH,
                confidence=MEDIUM,
                rationale=(
                    "Single authority, CRITICAL_RUNTIME, with test evidence. "
                    "It is load-bearing and appears healthy."
                ),
                action=(
                    "Freeze. Integrate it through the core's gateway without "
                    "modifying it. Revisit only with runtime evidence of a "
                    "defect."
                ),
                repositories=1,
                source_candidates=summary.source_candidates,
                test_candidates=summary.test_candidates,
                contract_candidates=summary.contract_candidates,
                repos=summary.repos,
                signals=tuple(signals),
            )

        if tested and contracted:
            return Decision(
                capability=summary.capability,
                layer=summary.layer,
                fragility=summary.fragility,
                mode=REUSE,
                confidence=HIGH,
                rationale=(
                    "Single authority with both test and contract evidence -- "
                    "the strongest static signal available."
                ),
                action=(
                    "Register it as a connector and let the core govern it. No "
                    "rewrite needed."
                ),
                repositories=1,
                source_candidates=summary.source_candidates,
                test_candidates=summary.test_candidates,
                contract_candidates=summary.contract_candidates,
                repos=summary.repos,
                signals=tuple(signals),
            )

        if tested and not contracted:
            return Decision(
                capability=summary.capability,
                layer=summary.layer,
                fragility=summary.fragility,
                mode=ADAPT,
                confidence=MEDIUM,
                rationale=(
                    "Single tested authority, but no contract at its boundary. "
                    "It works; nothing pins the shape it exchanges."
                ),
                action=(
                    "Write a contract describing what it already returns, then "
                    "register it as a connector. Adapt at the seam -- do not "
                    "change the implementation."
                ),
                repositories=1,
                source_candidates=summary.source_candidates,
                test_candidates=summary.test_candidates,
                contract_candidates=summary.contract_candidates,
                repos=summary.repos,
                signals=tuple(signals),
            )

        return Decision(
            capability=summary.capability,
            layer=summary.layer,
            fragility=summary.fragility,
            mode=HARDEN,
            confidence=HIGH if critical else MEDIUM,
            rationale=(
                "Single authority with no test evidence"
                + (" for a CRITICAL_RUNTIME capability." if critical else ".")
                + " Nothing proves it behaves as intended."
            ),
            action=(
                "Add a characterisation test for current behaviour first, then a "
                "contract, then register it. Tests before changes: the point is "
                "to discover what it does, not what it should do."
            ),
            repositories=1,
            source_candidates=summary.source_candidates,
            test_candidates=summary.test_candidates,
            contract_candidates=summary.contract_candidates,
            repos=summary.repos,
            signals=tuple(signals),
        )

    raise ValueError("Unhandled summary status: {}".format(summary.status))


@dataclass
class DecisionResult:
    """The full PPC-00B outcome."""

    decisions: List[Decision] = field(default_factory=list)
    evidence_dir: Optional[Path] = None
    manifest: Optional[Dict[str, Any]] = None

    def by_mode(self, mode: str) -> List[Decision]:
        return [item for item in self.decisions if item.mode == mode]

    def counts(self) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for item in self.decisions:
            totals[item.mode] = totals.get(item.mode, 0) + 1
        return totals

    def ordered(self) -> List[Decision]:
        """Decisions in the order the work should be attempted."""
        return sorted(
            self.decisions,
            key=lambda d: (d.priority, d.fragility != FRAGILITY_CRITICAL_RUNTIME, d.capability),
        )

    def render(self) -> str:
        lines = ["===== PPC-00B DECISION TABLE ====="]
        lines.extend(item.render() for item in self.ordered())
        lines.append("")
        lines.append("===== MODE COUNTS =====")
        for mode, count in sorted(self.counts().items()):
            lines.append("{}={}".format(mode, count))
        return "\n".join(lines)

    def render_plan(self) -> str:
        """The ordered work plan an operator can act on."""
        lines = ["===== RECOMMENDED SEQUENCE ====="]
        for index, item in enumerate(self.ordered(), start=1):
            lines.append(
                "{:>2}. [{}] {} :: {}".format(
                    index, item.mode, item.capability, util.truncate(item.action, 140)
                )
            )
        return "\n".join(lines)


def decide(summaries: Sequence[CapabilitySummary]) -> DecisionResult:
    """Run the decision table over every capability."""
    return DecisionResult(decisions=[decide_one(item) for item in summaries])


def from_scan(result: ScanResult) -> DecisionResult:
    return decide(result.summaries)


def persist(
    result: DecisionResult,
    *,
    safety: SafetyContract,
    evidence_root: Optional[Path] = None,
    source_evidence: Optional[str] = None,
) -> DecisionResult:
    """Write the decision artifacts and seal them."""
    run = EvidenceRun(work_id=WORK_ID, gate=GATE, safety=safety, root=evidence_root)

    run.write_tsv(
        "capability-decisions.tsv",
        [
            "capability", "layer", "fragility", "mode", "confidence",
            "repositories", "source_candidates", "test_candidates",
            "rationale", "action",
        ],
        [item.as_row() for item in result.ordered()],
    )
    run.write_json(
        "decision-detail.json",
        {
            "schemaVersion": 1,
            "workId": WORK_ID,
            "gate": GATE,
            "sourceEvidence": source_evidence,
            "counts": result.counts(),
            "decisions": [item.as_dict() for item in result.ordered()],
        },
    )
    run.write_text("recommended-sequence.txt", result.render_plan() + "\n")

    counts = result.counts()
    run.write_json(
        "final-decision.json",
        {
            "schemaVersion": 1,
            "workId": WORK_ID,
            "gate": GATE,
            "decision": "PASS",
            "capabilitiesResolved": len(result.decisions),
            "capabilitiesExpected": CAPABILITY_COUNT,
            "counts": counts,
            # This gate proposes. It never authorises, and never applies.
            "implementationAuthorized": False,
            "sourceMutationAuthorized": False,
            "advisoryOnly": True,
            "nextState": "PPC00C_INTEGRATION_SEQUENCING",
        },
    )

    manifest = run.seal(
        decision="PASS",
        next_state="PPC00C_INTEGRATION_SEQUENCING",
        required=[
            "capability-decisions.tsv",
            "decision-detail.json",
            "final-decision.json",
        ],
        summary={"counts": counts, "capabilities": len(result.decisions)},
    )

    result.evidence_dir = run.dir
    result.manifest = manifest
    return result
