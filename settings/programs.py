# settings/programs.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass(frozen=True)
class Program:
    name: str
    instructions_path: str

    # Experiment grid:
    Upos_values: List[float]
    PEO_time_values: List[float]
    KOH_targets: List[float]   # 0..1 as fraction of stock (if stock=1, water=0)

    # Mixing:
    total_ml: float
    # Two-channel model (recommended starter):
    water_channel: str = "CH1"
    koh_stock_channel: str = "CH2"
    water_conc: float = 0.0
    koh_stock_conc: float = 1.0  # treat as normalized stock


def list_programs() -> List[Program]:
    # Add more programs later; UI just selects by name.
    return [
        Program(
            name="KOH_scan_small",
            instructions_path="settings/instructions.txt",
            #Upos_values=[100, 300, 500],
            Upos_values=[100],
            PEO_time_values=[30],
            KOH_targets=[0.1, 0.3, 0.5],
            total_ml=20.0,
            water_channel="CH1",
            koh_stock_channel="CH2",
            water_conc=0.0,
            koh_stock_conc=1.0,
        ),
        Program(
            name="KOH_scan_full",
            instructions_path="settings/instructions.txt",
            Upos_values=[100, 200, 300, 400, 500],
            PEO_time_values=[20, 30],
            KOH_targets=[0.1, 0.2, 0.3, 0.4, 0.5],
            total_ml=20.0,
            water_channel="CH1",
            koh_stock_channel="CH2",
            water_conc=0.0,
            koh_stock_conc=1.0,
        ),
    ]


def programs_by_name():
    return {p.name: p for p in list_programs()}