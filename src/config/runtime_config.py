from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    peripheral_port: str
    peripheral_baudrate: int
    stepper_description: str
    stepper_baudrate: int
    spectrometer_description: str
    spectrometer_baudrate: int
    peo_description: str
    peo_baudrate: int
    peo_parity: str
    peo_stopbits: int
    peo_bytesize: int
    peo_Ipos: int
    peo_Uneg: int
    peo_Ineg: int
    peo_pulsepos: int
    peo_pause1: int
    peo_pulseneg: int
    peo_pause2: int
    peo_multiplier: int
    event_log_path: str = "settings/system_events.log"


def from_legacy_config(legacy_module) -> RuntimeConfig:
    return RuntimeConfig(
        peripheral_port=legacy_module.peripheral_pico_port,
        peripheral_baudrate=legacy_module.peripheral_pico_baudrate,
        stepper_description=legacy_module.stepper_description,
        stepper_baudrate=legacy_module.stepper_baudrate,
        spectrometer_description=legacy_module.spectroscope_description,
        spectrometer_baudrate=legacy_module.spectroscope_baudrate,
        peo_description=legacy_module.PEO_description,
        peo_baudrate=legacy_module.PEO_baudrate,
        peo_parity=legacy_module.PEO_parity,
        peo_stopbits=legacy_module.PEO_stopbits,
        peo_bytesize=legacy_module.PEO_bytesize,
        peo_Ipos=legacy_module.PEO_Ipos,
        peo_Uneg=legacy_module.PEO_Uneg,
        peo_Ineg=legacy_module.PEO_Ineg,
        peo_pulsepos=legacy_module.PEO_Pulsepos,
        peo_pause1=legacy_module.PEO_Pause1,
        peo_pulseneg=legacy_module.PEO_Pulseneg,
        peo_pause2=legacy_module.PEO_Pause2,
        peo_multiplier=legacy_module.PEO_Multiplier,
    )