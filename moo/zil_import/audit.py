"""
Translator coverage audit — records what the ZIL translator processed,
what landed in the bootstrap output, and (most importantly) what got
silently dropped.

A translator that drops a clause because a heuristic doesn't recognise
it produces a failure that surfaces mid-puzzle, far from the cause
(PUB-F's AND-wrapped M-ENTER/M-END is the canonical example).  This
audit captures every decision-point drop so the regen log is
self-describing and a baseline-ratchet test can fail when the drop
catalog grows.

Scope: drops-only.  We intentionally do NOT track every COND clause or
every translated form — that would balloon both the JSON and the
maintenance burden of the baseline.  Drops are the actionable signal.

Drop kinds tracked:

- ``m_clause_dropped`` — a routine handles an M-* lifecycle constant
  but the combined-clause emitter couldn't extract its body (no-op,
  AND-shape the splitter doesn't recognise, …).
- ``f_clause_dropped`` — same for F-* combat constants.
- ``verb_clause_dropped`` — VERB? atoms that ``_emit_verb_clauses``
  bailed out on (overlap across clauses) and that ended up in the
  routine's residual body instead of per-verb files.
- ``syntax_rule_dropped`` — a SYNTAX rule whose V-routine is in
  ``_SKIP_ROUTINES`` (parser will never reach that rule's body).
- ``unhandled_form`` — a top-level statement the translator emitted
  as a bare ``# ZIL: <unhandled-form>`` comment.

Drop kinds NOT tracked (deliberate):

- Nested expression handlers that fall back to ``# ZIL: ...`` — too
  noisy and usually benign (an unhandled subform inside a TELL string
  still produces working output).
- Routine-level emit decisions (action_owner vs substrate, dspec
  picks) — those are encoded in the file shebangs themselves.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class _RoutineRecord:
    """Per-routine status + drop list, emitted as the routines map value."""

    status: str  # "emitted" | "skipped"
    reason: str | None = None  # populated when status == "skipped"
    action_owner: tuple[str, bool] | None = None
    files: list[str] = field(default_factory=list)
    m_clauses: dict[str, str] = field(default_factory=dict)  # constant → "combined"|"per_clause"
    f_clauses: dict[str, str] = field(default_factory=dict)
    drops: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RegenAudit:
    """
    Accumulator for one regen.  The generator instantiates one per game,
    calls the ``add_*`` / ``record_*`` methods at decision points, and
    serialises it to ``coverage.json`` after the routines loop.
    """

    game: str
    routines: dict[str, _RoutineRecord] = field(default_factory=dict)

    def _routine(self, name: str) -> _RoutineRecord:
        rec = self.routines.get(name)
        if rec is None:
            rec = _RoutineRecord(status="emitted")
            self.routines[name] = rec
        return rec

    def record_emitted(
        self,
        name: str,
        *,
        action_owner: tuple[str, bool] | None = None,
        files: list[str] | None = None,
    ) -> None:
        """
        Mark a routine as successfully emitted.

        :param name: ZIL routine name.
        :param action_owner: ``(atom, is_room)`` of the owning room or
            object, or ``None`` for substrate routines.
        :param files: Verb-file paths the emission produced.
        """
        rec = self._routine(name)
        rec.status = "emitted"
        rec.reason = None
        rec.action_owner = action_owner
        if files:
            for f in files:
                if f not in rec.files:
                    rec.files.append(f)

    def record_skipped(self, name: str, reason: str) -> None:
        """
        Mark a routine as deliberately skipped (e.g. in ``_SKIP_ROUTINES``).

        :param name: ZIL routine name.
        :param reason: Short tag explaining why (e.g. ``"_SKIP_ROUTINES"``).
        """
        rec = self._routine(name)
        rec.status = "skipped"
        rec.reason = reason

    def record_file(self, name: str, file_path: str) -> None:
        """
        Attach an emitted verb-file path to a routine record.

        :param name: ZIL routine name.
        :param file_path: Relative path under the bootstrap output dir.
        """
        rec = self._routine(name)
        if file_path not in rec.files:
            rec.files.append(file_path)

    def record_m_clause(self, name: str, constant: str, mode: str) -> None:
        """
        Record how an M-* clause was emitted.

        :param name: ZIL routine name.
        :param constant: M-* constant (e.g. ``"M-BEG"``).
        :param mode: ``"combined"`` (combined emission) or
            ``"per_clause"`` (legacy per-clause file).
        """
        self._routine(name).m_clauses[constant] = mode

    def record_f_clause(self, name: str, constant: str, mode: str) -> None:
        """
        Record how an F-* combat clause was emitted.

        :param name: ZIL routine name.
        :param constant: F-* constant (e.g. ``"F-DEAD"``).
        :param mode: ``"combined"`` or ``"per_clause"``.
        """
        self._routine(name).f_clauses[constant] = mode

    def add_drop(self, name: str, kind: str, **details: Any) -> None:
        """
        Record one drop on the named routine.

        ``details`` becomes the JSON entry alongside ``kind``.
        Convention: include enough identifying info that the drop is
        human-actionable (constant name, verb atoms, source-form snippet).

        :param name: ZIL routine name.
        :param kind: Drop category (``"m_clause"``, ``"verb_clause"``,
            ``"syntax_rule"``, ``"unhandled_form"``, …).
        :param details: Free-form identifying fields.
        """
        drop = {"kind": kind, **details}
        self._routine(name).drops.append(drop)

    # ---- serialisation ----

    def to_dict(self) -> dict[str, Any]:
        """
        Render the accumulated audit as the ``coverage.json`` payload.

        :returns: A dict with ``game``, ``generated_at``, a ``summary``
            block, and the per-routine ``routines`` map.
        """
        routines_payload: dict[str, dict[str, Any]] = {}
        total_drops = 0
        emitted = 0
        skipped = 0
        for name, rec in sorted(self.routines.items()):
            entry: dict[str, Any] = {"status": rec.status}
            if rec.reason is not None:
                entry["reason"] = rec.reason
            if rec.action_owner is not None:
                entry["action_owner"] = list(rec.action_owner)
            if rec.files:
                entry["files"] = sorted(rec.files)
            if rec.m_clauses:
                entry["m_clauses"] = dict(sorted(rec.m_clauses.items()))
            if rec.f_clauses:
                entry["f_clauses"] = dict(sorted(rec.f_clauses.items()))
            if rec.drops:
                entry["drops"] = rec.drops
                total_drops += len(rec.drops)
            routines_payload[name] = entry
            if rec.status == "emitted":
                emitted += 1
            else:
                skipped += 1
        return {
            "game": self.game,
            "generated_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            "summary": {
                "routines_total": len(self.routines),
                "routines_emitted": emitted,
                "routines_skipped": skipped,
                "drops": total_drops,
            },
            "routines": routines_payload,
        }

    def write(self, output_dir: Path) -> Path:
        """
        Write ``coverage.json`` into the bootstrap output dir.

        :param output_dir: Bootstrap output directory.
        :returns: Path to the written file.
        """
        path = output_dir / "coverage.json"
        path.write_text(_json.dumps(self.to_dict(), indent=2, sort_keys=False))
        return path
