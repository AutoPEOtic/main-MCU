from __future__ import annotations

import settings.config as legacy_config

from src.config.runtime_config import from_legacy_config
from src.core.logging_utils import EventLogger
from src.core.models import ProgramDefinition
from src.devices.device_manager import DeviceManager
from src.engine.checkpoint_store import CheckpointStore
from src.engine.experiment_engine import ExperimentEngine
from src.supervisor.supervisor import Supervisor


def main() -> None:
    cfg = from_legacy_config(legacy_config)
    logger = EventLogger("settings/system_events.log")

    dm = DeviceManager(cfg, logger)
    cp = CheckpointStore("settings/checkpoints")
    engine = ExperimentEngine(dm, cp, logger)
    supervisor = Supervisor(dm, engine, cp, logger)

    program = ProgramDefinition(
        name="supervisor_smoke",
        instructions_path="settings/instructions_engine_smoke.txt",
        Upos_values=[520],
        PEO_time_values=[2],
        KOH_targets=[0.3],
        total_ml=20.0,
        water_channel="CH1",
        koh_stock_channel="CH2",
        water_conc=0.0,
        koh_stock_conc=1.0,
    )

    supervisor.load_program(program)
    supervisor.startup()

    try:
        supervisor.run_blocking(
            resume_runs=False,
            clear_run_checkpoint_on_success=False,
        )
        print(supervisor.runtime_snapshot())
    finally:
        supervisor.shutdown()


if __name__ == "__main__":
    main()