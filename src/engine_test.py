from __future__ import annotations

import settings.config as legacy_config

from src.config.runtime_config import from_legacy_config
from src.core.logging_utils import EventLogger
from src.core.models import ProgramDefinition
from src.devices.device_manager import DeviceManager
from src.engine.checkpoint_store import CheckpointStore
from src.engine.experiment_engine import ExperimentEngine
from src.engine.run_plan import build_run_plan, as_run_context


def main() -> None:
    cfg = from_legacy_config(legacy_config)
    logger = EventLogger("settings/system_events.log")
    dm = DeviceManager(cfg, logger)
    cp = CheckpointStore("settings/checkpoints")
    engine = ExperimentEngine(dm, cp, logger)

    program = ProgramDefinition(
        name="migration_test_program",
        instructions_path="settings/instructions.txt",
        Upos_values=[520],
        PEO_time_values=[2],
        KOH_targets=[0.3],
        total_ml=20.0,
        water_channel="CH1",
        koh_stock_channel="CH2",
        water_conc=0.0,
        koh_stock_conc=1.0,
    )

    runs = build_run_plan(program)
    ctx = as_run_context(program, runs[0], total_runs=len(runs))

    dm.startup_all()
    try:
        result = engine.execute_run(
            ctx=ctx,
            instructions_path=program.instructions_path,
            resume=False,
            clear_checkpoint_on_success=False,
        )
        print(result)
    finally:
        dm.shutdown_all()


if __name__ == "__main__":
    main()