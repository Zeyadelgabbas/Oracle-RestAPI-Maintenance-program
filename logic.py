"""
logic.py
========
Pure business logic.
"""

import config


def calculate_km_since_last_service(current_km: float, last_service_km: float) -> float:
    return current_km - last_service_km


def is_oil_change_due(km_since_last_service: float) -> bool:
    return km_since_last_service >= config.OIL_CHANGE_INTERVAL_KM


def remaining_km(km_since_last_service: float) -> float:
    return config.OIL_CHANGE_INTERVAL_KM - km_since_last_service
