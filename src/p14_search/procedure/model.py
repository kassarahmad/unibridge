"""The ERDIS scholarship procedure 2026/2027 as ONE model, from which everything else is derived:

- the workflow net (places, transitions, arcs) checked for soundness in code (soundness.py) and exported as PNML;
- the BPMN 2.0 diagram (docs/bpmn/scholarship.bpmn, scripts/build_scholarship_model.py);
- the state machine of the scholarship guide (guide.py replays the net).

Every step names the article of the ERDIS call it comes from (docs/PROCEDURE.md lists them with quotes).
Workflow net = Petri net with one source place `i`, one sink place `o`, every node on a path from i to o.
BPMN mapping: task -> transition; XOR split -> place with several output transitions; XOR merge -> place with
several input transitions; AND split/join -> transition with several output/input places; end events ->
transitions into `o` (one sink, as a workflow net requires).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    id: str  # transition id (= BPMN element id)
    name: str
    lane: str  # student | erdis
    kind: str  # task | event | gateway_branch
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    article: str | None = None
    date: str | None = None  # ISO date (deadline or indicative date), when the call gives one
    indicative: bool = False


@dataclass(frozen=True)
class Gateway:
    id: str  # BPMN gateway id
    kind: str  # xor_split | xor_merge | and_split | and_join
    place: str | None  # the place that implements an XOR gateway
    name: str = ""


STEPS: tuple[Step, ...] = (
    Step("t_call", "Call for applications published", "erdis", "event", ("i",), ("p_call",), "ART. 1"),
    Step("t_split", "Start parallel preparation", "student", "gateway_branch", ("p_call",), ("p_econ", "p_enrol")),
    # branch A: economic condition (XOR: residents in Italy vs family abroad)
    Step("t_dsu", "Sign the DSU and obtain the ISEE for the right to university study", "student", "task",
         ("p_econ",), ("p_econ_ready",), "ART. 8"),
    Step("t_parificato", "Submit legalised and translated documents for the ISEE parificato", "student", "task",
         ("p_econ",), ("p_econ_ready",), "ART. 11", "2026-08-28"),
    Step("t_apply", "Submit and confirm the online application", "student", "task", ("p_econ_ready",), ("p_applied",),
         "Art. 10", "2026-08-28"),
    # branch B: enrolment at the university
    Step("t_enrol", "Enrol at the university for 2026/2027", "student", "task", ("p_enrol",), ("p_enrolled",), "ART. 3"),
    Step("t_join", "Applications closed", "erdis", "gateway_branch", ("p_applied", "p_enrolled"), ("p_closed",)),
    Step("t_check", "Check merit and economic requirements", "erdis", "task", ("p_closed",), ("p_checked",), "ART. 14"),
    Step("t_provisional", "Publish provisional ranking", "erdis", "task", ("p_checked",), ("p_prov",), "ART. 15",
         "2026-09-15", indicative=True),
    # XOR: optional request for review
    Step("t_review_request", "Submit a request for review (within 5 days)", "student", "task", ("p_prov",), ("p_review",), "ART. 15"),
    Step("t_review_decision", "Decide on the request for review", "erdis", "task", ("p_review",), ("p_ready_final",), "ART. 15"),
    Step("t_no_review", "No request for review", "student", "gateway_branch", ("p_prov",), ("p_ready_final",), "ART. 15"),
    Step("t_final", "Publish final ranking", "erdis", "task", ("p_ready_final",), ("p_final",), "ART. 15",
         "2026-10-15", indicative=True),
    # XOR: outcome
    Step("t_not_awarded", "Not awarded or excluded", "erdis", "event", ("p_final",), ("o",), "ART. 20"),
    Step("t_awarded", "Scholarship awarded", "erdis", "gateway_branch", ("p_final",), ("p_awarded",), "ART. 15"),
    Step("t_pay_first", "Pay the first instalment(s)", "erdis", "task", ("p_awarded",), ("p_paid_first",), "ART. 17"),
    # XOR: merit for the balance
    Step("t_merit_ok", "Merit requirement for the balance met", "erdis", "gateway_branch", ("p_paid_first",), ("p_merit_ok",), "ART. 7"),
    Step("t_merit_fail", "Merit requirement not met by the last deadline", "erdis", "gateway_branch", ("p_paid_first",),
         ("p_merit_fail",), "ART. 21"),
    Step("t_pay_balance", "Pay the balance", "erdis", "event", ("p_merit_ok",), ("o",), "ART. 17"),
    Step("t_revoke", "Revoke the scholarship and recover the amounts", "erdis", "event", ("p_merit_fail",), ("o",), "ART. 21"),
)

GATEWAYS: tuple[Gateway, ...] = (
    Gateway("g_and_split", "and_split", None, "prepare in parallel"),
    Gateway("g_econ_split", "xor_split", "p_econ", "family income in Italy?"),
    Gateway("g_econ_merge", "xor_merge", "p_econ_ready"),
    Gateway("g_and_join", "and_join", None),
    Gateway("g_review_split", "xor_split", "p_prov", "request for review?"),
    Gateway("g_review_merge", "xor_merge", "p_ready_final"),
    Gateway("g_outcome", "xor_split", "p_final", "awarded?"),
    Gateway("g_merit", "xor_split", "p_paid_first", "merit for the balance?"),
)

SOURCE, SINK = "i", "o"


@dataclass
class Net:
    places: list[str] = field(default_factory=list)
    transitions: dict[str, Step] = field(default_factory=dict)

    @property
    def arcs(self) -> list[tuple[str, str]]:
        out = []
        for t in self.transitions.values():
            out += [(p, t.id) for p in t.inputs] + [(t.id, p) for p in t.outputs]
        return out


def build_net() -> Net:
    places: list[str] = []
    for s in STEPS:
        for p in (*s.inputs, *s.outputs):
            if p not in places:
                places.append(p)
    return Net(places, {s.id: s for s in STEPS})
