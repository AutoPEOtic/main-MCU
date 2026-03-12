from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from src.core.errors import ValidationError
from src.core.models import ProgramDefinition, RunContext


@dataclass(frozen=True)
class CompiledRun:
    run_index: int
    Upos: float
    PEO_time: float
    KOH_target: float
    total_ml: float
    mix_channels: Dict[str, float]
    mix_labels: Dict[str, float]


def compute_two_channel_recipe(program: ProgramDefinition, target: float) -> Tuple[Dict[str, float], Dict[str, float]]:
    c1 = program.water_conc
    c2 = program.koh_stock_conc

    if abs(c2 - c1) < 1e-12:
        raise ValidationError("water_conc equals koh_stock_conc")

    r_koh = (target - c1) / (c2 - c1)
    r_koh = max(0.0, min(1.0, r_koh))
    r_water = 1.0 - r_koh

    channels = {
        program.water_channel: round(r_water, 6),
        program.koh_stock_channel: round(r_koh, 6),
    }
    labels = {
        "H2O": round(r_water, 6),
        "KOH_stock": round(r_koh, 6),
    }
    return channels, labels


def build_run_plan(program: ProgramDefinition) -> List[CompiledRun]:
    runs: List[CompiledRun] = []
    i = 0
    for peo_time in program.PEO_time_values:
        for upos in program.Upos_values:
            for koh in program.KOH_targets:
                i += 1
                channels, labels = compute_two_channel_recipe(program, koh)
                runs.append(
                    CompiledRun(
                        run_index=i,
                        Upos=upos,
                        PEO_time=peo_time,
                        KOH_target=koh,
                        total_ml=program.total_ml,
                        mix_channels=channels,
                        mix_labels=labels,
                    )
                )
    return runs


def as_run_context(program: ProgramDefinition, run: CompiledRun, total_runs: int) -> RunContext:
    return RunContext(
        run_index=run.run_index,
        total_runs=total_runs,
        program_name=program.name,
        Upos=run.Upos,
        PEO_time=run.PEO_time,
        KOH_target=run.KOH_target,
        total_ml=run.total_ml,
        mix_channels=run.mix_channels,
        mix_labels=run.mix_labels,
    )