"""internet engine — DECLARED DEFERRAL (not dead code, not yet built).

EDOS has NO live external-source capability today: fetching authoritative external sources (datasheets,
standards, part databases) for retrieval + citation is a real roadmap capability, but it is BLOCKED on a
human decision, not on engineering. That gap must be *visible*, not buried in a bare `NotImplementedError`.

Roadmap home: **CP-20 (Domain Grounding + Watchdog)** shipped the ingestion mechanism and citation path but
deliberately deferred *which* external sources to ingest — see **OD-9** in `BACKLOG-PHASE2.md` (Open
Decisions Register): "Domain sources + licensing (which standards/datasheets/part-DB) — undecided, human
pick (licensing matters)." Until OD-9 is decided, no live fetcher is wired here — by design (STOP condition:
do not fabricate a source list).

When OD-9 is resolved, implement the fetcher for the chosen sources behind this module and wire it into the
domain-grounding ingest path. Nothing imports this module yet; that is intentional (a declared gap), not an
oversight.
"""


def not_implemented(*_args, **_kwargs):
    raise NotImplementedError(
        "external-source fetch is deferred pending OD-9 (source + licensing decision) — see module docstring"
    )
