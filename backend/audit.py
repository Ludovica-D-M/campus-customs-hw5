"""Append-only audit trail for the agent team.

`output/audit_trail.json` holds a JSON array of run records. Every run appends
one record; earlier records are never rewritten, so the file is a history of
every execution rather than a snapshot of the last one.

Steps are flushed to disk as they happen, not at the end, so a run that hits a
limit or crashes still leaves a readable trail of how far it got.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models import AuditStep, RunRecord, now_stamp

HW_ROOT = Path(__file__).resolve().parent.parent
TRAIL_PATH = HW_ROOT / "output" / "audit_trail.json"


class AuditTrail:
    """Collects steps for one run and appends the run to the shared file."""

    def __init__(self, run_id: str, model: str, limits: dict[str, Any]) -> None:
        self.record = RunRecord(
            run_id=run_id, started_at=now_stamp(), model=model, limits=limits
        )
        self._step_no = 0
        self._append_to_file()

    def log(
        self,
        agent: str,
        event: str,
        detail: str = "",
        ticket_id: int | None = None,
        data: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
    ) -> AuditStep:
        self._step_no += 1
        step = AuditStep(
            run_id=self.record.run_id,
            step=self._step_no,
            agent=agent,
            event=event,  # type: ignore[arg-type]
            ticket_id=ticket_id,
            detail=detail,
            data=data or {},
            usage=usage or {},
        )
        self.record.steps.append(step)
        self._append_to_file()
        return step

    def finish(
        self,
        total_usage: dict[str, Any] | None = None,
        stopped_early: bool = False,
        stop_reason: str | None = None,
    ) -> None:
        self.record.finished_at = now_stamp()
        self.record.total_usage = total_usage or {}
        self.record.stopped_early = stopped_early
        self.record.stop_reason = stop_reason
        self._append_to_file()

    # ---------------------------------------------------------------- io

    def _read_all(self) -> list[dict[str, Any]]:
        """Read the existing runs, tolerating a missing or unreadable file.

        A corrupt file is kept, not silently dropped: it is moved aside with a
        .corrupt suffix so no previous record is ever lost to this process.
        """
        if not TRAIL_PATH.exists():
            return []
        try:
            data = json.loads(TRAIL_PATH.read_text())
        except json.JSONDecodeError:
            TRAIL_PATH.replace(TRAIL_PATH.with_suffix(".json.corrupt"))
            return []
        return data if isinstance(data, list) else [data]

    def _append_to_file(self) -> None:
        """Rewrite this run's entry in place, leaving every earlier run alone."""
        TRAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
        runs = self._read_all()
        mine = self.record.model_dump(mode="json")
        for i, run in enumerate(runs):
            if run.get("run_id") == self.record.run_id:
                runs[i] = mine
                break
        else:
            runs.append(mine)
        TRAIL_PATH.write_text(json.dumps(runs, indent=2) + "\n")
