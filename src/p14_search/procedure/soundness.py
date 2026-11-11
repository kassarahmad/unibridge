"""Workflow-net checks in plain Python (no dependency), cross-checked with pm4py when it is installed.

Soundness (van der Aalst) for a workflow net with source i and sink o:
1. option to complete: from every marking reachable from [i], the marking [o] is reachable;
2. proper completion: every reachable marking with a token in o is exactly [o];
3. no dead transitions: every transition is enabled in some reachable marking.
The reachability graph is explored exhaustively (the net is small and must be bounded: a bound guard stops
the search if a place ever holds more than BOUND tokens, which would itself mean "not sound").
"""

from __future__ import annotations

from collections import Counter, deque

from p14_search.procedure.model import SINK, SOURCE, Net

BOUND = 5
Marking = tuple[tuple[str, int], ...]


def _key(m: Counter) -> Marking:
    return tuple(sorted((p, n) for p, n in m.items() if n))


def enabled(net: Net, m: Counter) -> list[str]:
    return [t.id for t in net.transitions.values() if all(m[p] >= 1 for p in t.inputs)]


def fire(net: Net, m: Counter, tid: str) -> Counter:
    t = net.transitions[tid]
    n = Counter(m)
    for p in t.inputs:
        n[p] -= 1
    for p in t.outputs:
        n[p] += 1
    return n


def is_workflow_net(net: Net) -> dict:
    inputs = {p: 0 for p in net.places}
    outputs = {p: 0 for p in net.places}
    for src, dst in net.arcs:
        if src in outputs:
            outputs[src] += 1
        if dst in inputs:
            inputs[dst] += 1
    sources = [p for p in net.places if inputs[p] == 0]
    sinks = [p for p in net.places if outputs[p] == 0]
    # every node on a path from i to o: forward reachability from i and backward from o
    succ, pred = {}, {}
    for a, b in net.arcs:
        succ.setdefault(a, set()).add(b)
        pred.setdefault(b, set()).add(a)

    def reach(start, edges):
        seen, todo = {start}, [start]
        while todo:
            for nxt in edges.get(todo.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen

    nodes = set(net.places) | set(net.transitions)
    on_path = reach(SOURCE, succ) & reach(SINK, pred)
    return {"sources": sources, "sinks": sinks, "single_source_i": sources == [SOURCE], "single_sink_o": sinks == [SINK],
            "nodes_not_on_i_o_path": sorted(nodes - on_path),
            "ok": sources == [SOURCE] and sinks == [SINK] and on_path == nodes}


def reachability(net: Net) -> tuple[dict[Marking, list[tuple[str, Marking]]], bool]:
    start = Counter({SOURCE: 1})
    graph: dict[Marking, list[tuple[str, Marking]]] = {}
    todo = deque([start])
    bounded = True
    while todo:
        m = todo.popleft()
        k = _key(m)
        if k in graph:
            continue
        graph[k] = []
        for tid in enabled(net, m):
            n = fire(net, m, tid)
            if max(n.values(), default=0) > BOUND:
                bounded = False
                continue
            graph[k].append((tid, _key(n)))
            if _key(n) not in graph:
                todo.append(n)
    return graph, bounded


def check_soundness(net: Net) -> dict:
    wf = is_workflow_net(net)
    graph, bounded = reachability(net)
    final = _key(Counter({SINK: 1}))
    # option to complete: backward reachability of [o] in the reachability graph
    reverse: dict[Marking, set[Marking]] = {k: set() for k in graph}
    for k, edges in graph.items():
        for _, n in edges:
            reverse.setdefault(n, set()).add(k)
    can_finish, todo = {final}, [final]
    while todo:
        for prev in reverse.get(todo.pop(), ()):
            if prev not in can_finish:
                can_finish.add(prev)
                todo.append(prev)
    stuck = [dict(k) for k in graph if k not in can_finish]
    improper = [dict(k) for k in graph if dict(k).get(SINK, 0) >= 1 and k != final]
    fired = {tid for edges in graph.values() for tid, _ in edges}
    dead = sorted(set(net.transitions) - fired)
    return {
        "workflow_net": wf,
        "reachable_markings": len(graph),
        "bounded": bounded,
        "option_to_complete": not stuck,
        "proper_completion": not improper,
        "no_dead_transitions": not dead,
        "dead_transitions": dead,
        "markings_that_cannot_complete": stuck[:5],
        "sound": wf["ok"] and bounded and not stuck and not improper and not dead,
    }


def pm4py_check(pnml_path: str) -> dict:
    """Independent check with pm4py (Woflan) on the exported PNML file. Returns {'available': False} without pm4py."""
    try:
        import pm4py
    except ImportError:
        return {"available": False}
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the PNML has no final marking (kept WoPeD-compatible): set [o] here
        net, im, fm = pm4py.read_pnml(pnml_path)
    if not fm:
        fm = pm4py.generate_marking(net, {SINK: 1})
    return {"available": True, "version": getattr(pm4py, "__version__", None),
            "is_sound": bool(pm4py.check_soundness(net, im, fm)[0]), "places": len(net.places), "transitions": len(net.transitions)}
