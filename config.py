"""
config.py
=========
Loads configuration from .env.

This version separates:
- completed service statuses: count as real last oil service
- canceled statuses: terminal, but do NOT count as service
- open statuses: prevent duplicate work order creation
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def _require(var_name: str) -> str:
    value = os.getenv(var_name)
    if value is None or str(value).strip() == "":
        raise EnvironmentError(f"[CONFIG ERROR] Required variable '{var_name}' is missing from .env")
    return str(value).strip()


def _optional(var_name: str, default: str = "") -> str:
    value = os.getenv(var_name)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def _as_int(var_name: str) -> int:
    try:
        return int(_require(var_name))
    except ValueError as exc:
        raise EnvironmentError(f"[CONFIG ERROR] {var_name} must be an integer.") from exc


def _as_bool(var_name: str, default: str = "false") -> bool:
    return _optional(var_name, default).lower() in {"1", "true", "yes", "y"}


ORACLE_BASE_URL = _require("ORACLE_BASE_URL").rstrip("/")
ORACLE_API_VERSION = _optional("ORACLE_API_VERSION", "11.13.18.05")

ORACLE_USERNAME = _require("ORACLE_USERNAME")
ORACLE_PASSWORD = _require("ORACLE_PASSWORD")

ORG_CODE = _require("ORG_CODE")
ITEM_NUMBER = _require("ITEM_NUMBER")
METER_CODE = _require("METER_CODE")

CONDITION_EVENT_CODE = _require("CONDITION_EVENT_CODE")
WORK_DEFINITION_NAME = _require("WORK_DEFINITION_NAME")
OIL_CHANGE_INTERVAL_KM = _as_int("OIL_CHANGE_INTERVAL_KM")

# These are text fragments, not only exact values.
# This handles statuses like "Closed", "ORA_CLOSED", "Completed", "ORA_COMPLETED".
COMPLETED_STATUS_KEYWORDS = [
    s.strip().lower()
    for s in _optional("COMPLETED_STATUS_KEYWORDS", "closed,complete,completed").split(",")
    if s.strip()
]

CANCELED_STATUS_KEYWORDS = [
    s.strip().lower()
    for s in _optional("CANCELED_STATUS_KEYWORDS", "cancel,canceled,cancelled").split(",")
    if s.strip()
]

OPEN_STATUS_KEYWORDS = [
    s.strip().lower()
    for s in _optional("OPEN_STATUS_KEYWORDS", "draft,unreleased,released,on hold,hold,open").split(",")
    if s.strip()
]

# If True, main.py prints all work orders found for each asset so we can discover
# your instance's real status names, work-definition fields, and date fields.
DEBUG_WORK_ORDERS = _as_bool("DEBUG_WORK_ORDERS", "false")

# If True, script will not create condition-event WOs. Good for testing logic.
DRY_RUN = _as_bool("DRY_RUN", "false")
