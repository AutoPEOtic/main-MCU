import settings.config as legacy_config

from src.config.runtime_config import from_legacy_config
from src.core.logging_utils import EventLogger
from src.devices.device_manager import DeviceManager

cfg = from_legacy_config(legacy_config)
logger = EventLogger("settings/system_events.log")
dm = DeviceManager(cfg, logger)

dm.startup_all()

print(dm.send_peripheral_text("STATUS", timeout_s=5.0))
print(dm.send_motion_config("$X", wait_idle=False))
print(dm.peo_off())

dm.shutdown_all()