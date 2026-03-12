from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from src.core.models import RunContext


_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_name(value: str) -> str:
    value = value.strip().replace(" ", "_")
    value = _SAFE_RE.sub("_", value)
    return value or "unnamed"


@dataclass
class CheckpointRecord:
    program_name: str
    run_index: int
    total_runs: int
    action_index: int
    total_actions: int
    action_name: str
    status: str
    params: Dict[str, Any]
    updated_at: float


class CheckpointStore:
    """
    One checkpoint file per run.
    The checkpoint marks the latest successfully completed action index.
    """

    def __init__(self, root_dir: str = "settings/checkpoints") -> None:
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)

    def _path_for(self, ctx: RunContext) -> str:
        program = _safe_name(ctx.program_name)
        filename = f"{program}__run_{ctx.run_index:03d}.json"
        return os.path.join(self.root_dir, filename)

    def save_success(
        self,
        ctx: RunContext,
        action_index: int,
        total_actions: int,
        action_name: str,
    ) -> None:
        record = CheckpointRecord(
            program_name=ctx.program_name,
            run_index=ctx.run_index,
            total_runs=ctx.total_runs,
            action_index=action_index,
            total_actions=total_actions,
            action_name=action_name,
            status="SUCCESS",
            params={
                "Upos": ctx.Upos,
                "PEO_time": ctx.PEO_time,
                "KOH_target": ctx.KOH_target,
                "total_ml": ctx.total_ml,
                "mix_channels": ctx.mix_channels,
                "mix_labels": ctx.mix_labels,
            },
            updated_at=time.time(),
        )
        path = self._path_for(ctx)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def load(self, ctx: RunContext) -> Optional[CheckpointRecord]:
        path = self._path_for(ctx)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return CheckpointRecord(
            program_name=raw["program_name"],
            run_index=int(raw["run_index"]),
            total_runs=int(raw["total_runs"]),
            action_index=int(raw["action_index"]),
            total_actions=int(raw["total_actions"]),
            action_name=str(raw["action_name"]),
            status=str(raw["status"]),
            params=dict(raw.get("params", {})),
            updated_at=float(raw["updated_at"]),
        )

    def clear(self, ctx: RunContext) -> None:
        path = self._path_for(ctx)
        if os.path.exists(path):
            os.remove(path)

    def mark_failed(
        self,
        ctx: RunContext,
        action_index: int,
        total_actions: int,
        action_name: str,
        error_text: str,
    ) -> None:
        record = CheckpointRecord(
            program_name=ctx.program_name,
            run_index=ctx.run_index,
            total_runs=ctx.total_runs,
            action_index=action_index,
            total_actions=total_actions,
            action_name=action_name,
            status=f"FAILED: {error_text}",
            params={
                "Upos": ctx.Upos,
                "PEO_time": ctx.PEO_time,
                "KOH_target": ctx.KOH_target,
                "total_ml": ctx.total_ml,
                "mix_channels": ctx.mix_channels,
                "mix_labels": ctx.mix_labels,
            },
            updated_at=time.time(),
        )
        path = self._path_for(ctx)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)