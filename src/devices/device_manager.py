from __future__ import annotations

from typing import Dict, Iterable, Optional

from src.config.runtime_config import RuntimeConfig
from src.core.errors import DeviceUnhealthyError, ValidationError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceName, DeviceTrust


from src.devices.motion_worker import MotionWorker
from src.devices.peripheral_worker import PeripheralWorker
from src.devices.peo_worker import PEOWorker
from src.devices.spectrometer_worker import SpectrometerWorker

from src.transport.legacy_adapters import (
    LegacyMotionAdapter,
    LegacyPEOAdapter,
    LegacyPeripheralAdapter,
    LegacySpectrometerAdapter,
    cycle_usb_hubs,
)


class DeviceManager:
    def __init__(self, cfg: RuntimeConfig, logger: EventLogger) -> None:
        self.cfg = cfg
        self.logger = logger

        self.peripheral = PeripheralWorker(LegacyPeripheralAdapter(cfg), logger)
        self.motion = MotionWorker(LegacyMotionAdapter(cfg), logger)
        self.spectrometer = SpectrometerWorker(LegacySpectrometerAdapter(cfg), logger)
        self.peo = PEOWorker(LegacyPEOAdapter(cfg), logger)

        self._workers: Dict[DeviceName, object] = {
            DeviceName.PERIPHERAL: self.peripheral,
            DeviceName.MOTION: self.motion,
            DeviceName.SPECTROMETER: self.spectrometer,
            DeviceName.PEO: self.peo,
        }

    def startup_all(self) -> None:
        self.logger.info("device_manager", "all", "STARTUP_ALL", "START")
        for name in (DeviceName.PERIPHERAL, DeviceName.MOTION, DeviceName.SPECTROMETER, DeviceName.PEO):
            self.open_device(name)
        self.logger.info("device_manager", "all", "STARTUP_ALL", "OK")

    def shutdown_all(self) -> None:
        self.logger.info("device_manager", "all", "SHUTDOWN_ALL", "START")
        for worker in self._workers.values():
            try:
                worker.close()
            except Exception as exc:
                self.logger.error("device_manager", "all", "SHUTDOWN_ALL", detail=str(exc))
        self.logger.info("device_manager", "all", "SHUTDOWN_ALL", "OK")

    def open_device(self, name: DeviceName) -> None:
        worker = self._workers[name]
        worker.open()
        worker.healthcheck()

    def healthcheck_device(self, name: DeviceName) -> None:
        self._workers[name].healthcheck()

    def reconnect_device(self, name: DeviceName) -> None:
        self.logger.info("device_manager", name.value, "RECONNECT_DEVICE", "START")
        worker = self._workers[name]
        worker.reconnect()
        self.logger.info("device_manager", name.value, "RECONNECT_DEVICE", "OK")

    def reconnect_all(self, cycle_bus: bool = True) -> None:
        self.logger.info("device_manager", "all", "RECONNECT_ALL", "START", cycle_bus=cycle_bus)

        # explicit close first
        for worker in self._workers.values():
            try:
                worker.close()
            except Exception as exc:
                self.logger.error("device_manager", "all", "CLOSE_BEFORE_RECONNECT", detail=str(exc))

        if cycle_bus:
            cycle_usb_hubs()

        for name in (DeviceName.PERIPHERAL, DeviceName.MOTION, DeviceName.SPECTROMETER, DeviceName.PEO):
            self.open_device(name)

        self.logger.info("device_manager", "all", "RECONNECT_ALL", "OK", cycle_bus=cycle_bus)

    def snapshot_devices(self) -> Dict[str, object]:
        return {name.value: worker.snapshot() for name, worker in self._workers.items()}

    # ---------- dispatch API for Engine ----------

    def send_motion(self, cmd: str) -> CommandResult:
        return self.motion.execute_motion(cmd)

    def send_motion_config(self, cmd: str, wait_idle: bool = False) -> CommandResult:
        return self.motion.execute_config(cmd, wait_idle=wait_idle)

    def home_motion(self) -> CommandResult:
        return self.motion.execute_home()

    def send_peripheral_text(self, cmd: str, timeout_s: float) -> CommandResult:
        return self.peripheral.execute_text(cmd, timeout_s=timeout_s)

    def send_solution(self, total_ml: float, channels: dict[str, float], timeout_s: float) -> CommandResult:
        return self.peripheral.execute_solution(total_ml=total_ml, channels=channels, timeout_s=timeout_s)

    def acquire_spectrum(self) -> CommandResult:
        return self.spectrometer.execute_acquire()

    def peo_send_values(self, upos: float) -> CommandResult:
        return self.peo.execute_send_values(upos)

    def peo_on(self, peo_time_s: float) -> CommandResult:
        return self.peo.execute_on(peo_time_s)

    def peo_off(self) -> CommandResult:
        return self.peo.execute_off()
    
    def recover_motion_basic(self) -> None:
        self.logger.info("device_manager", "motion", "RECOVER_MOTION_BASIC", "START")
        self.reconnect_device(DeviceName.MOTION)
        self.send_motion_config("$X", wait_idle=False)
        self.healthcheck_device(DeviceName.MOTION)
        self.logger.info("device_manager", "motion", "RECOVER_MOTION_BASIC", "OK")

    def recover_peripheral_basic(self, do_home_all: bool = False) -> None:
        self.logger.info(
            "device_manager",
            "peripheral",
            "RECOVER_PERIPHERAL_BASIC",
            "START",
            do_home_all=do_home_all,
        )
        self.reconnect_device(DeviceName.PERIPHERAL)
        self.send_peripheral_text("STATUS", timeout_s=5.0)
        if do_home_all:
            self.send_peripheral_text("HOME ALL", timeout_s=180.0)
        self.logger.info(
            "device_manager",
            "peripheral",
            "RECOVER_PERIPHERAL_BASIC",
            "OK",
            do_home_all=do_home_all,
        )

    def device_trust(self, name: DeviceName) -> str:
        return self._workers[name].trust.value