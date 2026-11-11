"""Citation verifier for generated answers.

Step 1 (always): split the model output into sentences; keep a sentence only if it ends with one or more
citation aliases and every alias belongs to the passages that were retrieved for this request. Text
without a citation, or citing an unknown alias, is dropped (counted, never shown).
Step 2 (optional): ask the same LLM whether the cited passage supports the sentence (yes/no, cached);
unsupported sentences are dropped too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CITES = re.compile(r"((?:\s*\[\s*P\d+(?:\s*[,;]\s*P?\d+)*\s*\])+)\s*")
_ALIAS = re.compile(r"P?(\d+)")
# Split after . ! ? and the Arabic question mark when a new sentence starts (letter or quote), but not after
# common abbreviations such as "Art." or "a.a.".
_SPLIT = re.compile(r"(?<=[.!?؟])\s+(?=[\"“(A-ZÀ-Ü؀-ۿ])")
_ABBREV = re.compile(r"(?:\b(?:art|artt|n|nn|lett|pag|ecc|es|cfr|prof|dott|sig|e\.g|i\.e|a\.a|a\.y)\.)$", re.IGNORECASE)


@dataclass
class Claim:
    text: str
    aliases: list[str]


@dataclass
class Verification:
    kept: list[Claim] = field(default_factory=list)
    dropped_uncited: list[str] = field(default_factory=list)
    dropped_invalid: list[Claim] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    for piece in _SPLIT.split(text.strip()):
        if parts and _ABBREV.search(parts[-1]):
            parts[-1] = f"{parts[-1]} {piece}"
        else:
            parts.append(piece)
    return [p.strip() for p in parts if p.strip()]


def parse_claims(output: str) -> tuple[list[Claim], list[str]]:
    """(cited claims, uncited sentences). Only the LAST sentence before a citation group receives it."""
    claims: list[Claim] = []
    uncited: list[str] = []
    pos = 0
    for m in _CITES.finditer(output):
        chunk = output[pos:m.start()]
        pos = m.end()
        sents = _sentences(chunk)
        if not sents:
            continue
        uncited.extend(sents[:-1])
        aliases = [f"P{n}" for n in _ALIAS.findall(m.group(1))]
        claims.append(Claim(sents[-1], list(dict.fromkeys(aliases))))
    uncited.extend(s for s in _sentences(output[pos:]) if re.search(r"\w", s))
    return claims, uncited


def verify_citations(output: str, valid_aliases: set[str]) -> Verification:
    claims, uncited = parse_claims(output)
    v = Verification(dropped_uncited=uncited)
    for c in claims:
        (v.kept if c.aliases and all(a in valid_aliases for a in c.aliases) else v.dropped_invalid).append(c)
    return v


def is_yes(text: str) -> bool:
    return text.strip().strip(".").lower().startswith(("yes", "sì", "si"))
