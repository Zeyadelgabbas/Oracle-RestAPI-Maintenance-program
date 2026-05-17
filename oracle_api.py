"""
oracle_api.py
=============
Oracle Fusion REST API functions.

Critical fix:
- For the wrapper action body, POST to /maintenanceWorkOrders.
- Do NOT post the wrapper body to /maintenanceWorkOrders/action/createConditionBasedWorkOrders.
- Your Oracle GET showed EventCode = ZE2_OIL_CODE, so .env must use:
  CONDITION_EVENT_CODE=ZE2_OIL_CODE
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

import auth
import config


@dataclass
class ServiceInfo:
    km: float
    work_order_number: str | None = None
    completion_date: datetime | None = None
    status: str | None = None
    reason: str = ""


@dataclass
class OpenWorkOrderInfo:
    exists: bool
    work_order_number: str | None = None
    status: str | None = None
    reason: str = ""


def _api_url(resource_path: str) -> str:
    return (
        f"{config.ORACLE_BASE_URL}/fscmRestApi/resources/"
        f"{config.ORACLE_API_VERSION}/{resource_path.lstrip('/')}"
    )


def _handle_response(response: requests.Response, context: str) -> dict:
    if not response.ok:
        raise requests.HTTPError(
            f"\n[API ERROR] {context}\n"
            f"  Status Code : {response.status_code}\n"
            f"  URL         : {response.url}\n"
            f"  Response    : {response.text[:1500]}\n"
        )

    if not response.text.strip():
        return {"status": "success", "status_code": response.status_code}

    try:
        return response.json()
    except ValueError:
        return {
            "status": "success",
            "status_code": response.status_code,
            "raw_response": response.text,
        }


def _get(resource_path: str, params: dict | None, context: str) -> dict:
    response = requests.get(
        _api_url(resource_path),
        headers=auth.get_headers(),
        params=params or {},
        timeout=60,
    )
    return _handle_response(response, context)


def _post_action(resource_path: str, payload: dict, context: str) -> dict:
    headers = auth.get_headers()
    headers["Accept"] = "application/json"
    headers["Content-Type"] = "application/vnd.oracle.adf.action+json"

    response = requests.post(
        _api_url(resource_path),
        headers=headers,
        json=payload,
        timeout=60,
    )
    return _handle_response(response, context)


def _get_all(resource_path: str, params: dict | None, context: str, limit: int = 100) -> list[dict]:
    out: list[dict] = []
    offset = 0
    base_params = dict(params or {})

    while True:
        request_params = dict(base_params)
        request_params["limit"] = limit
        request_params["offset"] = offset

        data = _get(resource_path, request_params, context)
        items = data.get("items", [])
        out.extend(items)

        if not data.get("hasMore", False):
            break
        offset += limit

    return out


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip().lower()


def _contains_any(value: Any, keywords: list[str]) -> bool:
    v = _norm(value).replace("_", " ").replace("-", " ")
    return any(k in v for k in keywords)


def _first_present(row: dict, names: list[str]) -> Any:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name)
    return None


def _parse_oracle_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def wo_number(wo: dict) -> str:
    return str(_first_present(wo, ["WorkOrderNumber", "WorkOrderName", "WoNumber", "Name", "WorkOrder"]) or "")


def wo_status(wo: dict) -> str:
    return str(_first_present(wo, ["StatusCode", "WorkOrderStatusCode", "Status", "WorkOrderStatus"]) or "")


def wo_work_definition(wo: dict) -> str:
    return str(_first_present(wo, ["WorkDefinitionName", "WorkDefinitionCode", "WorkDefinition"]) or "")


def wo_completion_dt(wo: dict) -> datetime | None:
    value = _first_present(
        wo,
        [
            "ActualCompletionDate",
            "ActualCompletionDateTime",
            "CompletionDate",
            "CompletedDate",
            "ClosedDate",
            "LastUpdateDate",
        ],
    )
    return _parse_oracle_datetime(value)


def wo_summary(wo: dict) -> dict:
    return {
        "WorkOrderNumber": wo_number(wo),
        "Status": wo_status(wo),
        "WorkDefinition": wo_work_definition(wo),
        "CompletionDate": str(_first_present(wo, ["ActualCompletionDate", "ActualCompletionDateTime", "CompletionDate", "CompletedDate", "ClosedDate", "LastUpdateDate"]) or ""),
        "Description": str(_first_present(wo, ["WorkOrderDescription", "Description", "WorkOrderName"]) or ""),
        "Keys": sorted(list(wo.keys()))[:60],
    }


def is_completed_service_status(status: Any) -> bool:
    if _contains_any(status, config.CANCELED_STATUS_KEYWORDS):
        return False
    return _contains_any(status, config.COMPLETED_STATUS_KEYWORDS)


def is_canceled_status(status: Any) -> bool:
    return _contains_any(status, config.CANCELED_STATUS_KEYWORDS)


def is_open_status(status: Any) -> bool:
    if not status:
        return False
    if is_completed_service_status(status) or is_canceled_status(status):
        return False
    return _contains_any(status, config.OPEN_STATUS_KEYWORDS)


def matches_oil_work_definition(wo: dict) -> bool:
    configured = _norm(config.WORK_DEFINITION_NAME)
    if not configured:
        return True

    candidates = [
        wo_work_definition(wo),
        _first_present(wo, ["WorkOrderDescription", "Description", "WorkOrderName"]),
    ]
    return any(configured in _norm(c) for c in candidates if c)


def get_all_cars() -> list[dict]:
    params = {
        "q": f"ItemNumber={config.ITEM_NUMBER};OperatingOrganizationCode={config.ORG_CODE}",
        "fields": "AssetId,AssetNumber",
    }
    return _get_all("installedBaseAssets", params, "Fetching fleet cars", limit=100)


def _reading_value(row: dict) -> float | None:
    value = _first_present(row, ["ReadingValue", "Reading", "DisplayedReading", "LifeToDateReading"])
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reading_date(row: dict) -> Any:
    return _first_present(row, ["ReadingDate", "ReadingDateTime", "ReadingDateTimeValue", "CreationDate"])


def get_meter_readings(asset_number: str, limit: int = 200) -> list[dict]:
    params = {
        "finder": (
            f"MetersByAssetMeterUserKey;"
            f"MntAssetNumber={asset_number},"
            f"MntMeterCode={config.METER_CODE}"
        ),
        "fields": "AssetNumber,MeterCode,ReadingValue,ReadingDate",
        "orderBy": "ReadingDate:desc",
        "limit": limit,
    }

    try:
        data = _get("meterReadings", params, f"Fetching meter readings for {asset_number}")
        return data.get("items", [])
    except requests.HTTPError:
        fallback = {
            "finder": (
                f"MetersByAssetMeterUserKey;"
                f"MntAssetNumber={asset_number},"
                f"MntMeterCode={config.METER_CODE}"
            ),
            "limit": limit,
        }
        data = _get("meterReadings", fallback, f"Fetching meter readings for {asset_number} fallback")
        items = data.get("items", [])
        return sorted(
            items,
            key=lambda r: _parse_oracle_datetime(_reading_date(r)) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )


def get_latest_odometer_reading(asset_number: str) -> float | None:
    rows = get_meter_readings(asset_number, limit=1)
    if not rows:
        return None
    return _reading_value(rows[0])


def get_latest_odometer_reading_before(asset_number: str, target_dt: datetime) -> float | None:
    rows = get_meter_readings(asset_number, limit=200)
    best_dt: datetime | None = None
    best_value: float | None = None

    for row in rows:
        row_dt = _parse_oracle_datetime(_reading_date(row))
        row_value = _reading_value(row)

        if row_dt is None or row_value is None:
            continue

        if row_dt <= target_dt and (best_dt is None or row_dt > best_dt):
            best_dt = row_dt
            best_value = row_value

    return best_value


def get_work_orders_for_asset(asset_number: str, asset_id: Any | None = None) -> list[dict]:
    queries = [f"AssetNumber={asset_number}"]
    if asset_id not in (None, ""):
        queries.append(f"AssetId={asset_id}")

    for q in queries:
        try:
            rows = _get_all(
                "maintenanceWorkOrders",
                {"q": q, "limit": 100},
                f"Fetching work orders with {q}",
                limit=100,
            )
            if rows:
                return rows
        except requests.HTTPError:
            continue

    return []


def get_last_completed_oil_change_info(asset_number: str, asset_id: Any | None = None) -> ServiceInfo:
    wos = get_work_orders_for_asset(asset_number, asset_id)

    candidates: list[tuple[datetime, dict]] = []
    for wo in wos:
        status = wo_status(wo)

        if not matches_oil_work_definition(wo):
            continue
        if is_canceled_status(status):
            continue
        if not is_completed_service_status(status):
            continue

        completed_at = wo_completion_dt(wo)
        if completed_at is None:
            continue

        candidates.append((completed_at, wo))

    if not candidates:
        return ServiceInfo(
            km=0.0,
            reason="No completed/closed oil-change WO found. Canceled WOs do not count as service.",
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    completed_at, wo = candidates[0]
    km = get_latest_odometer_reading_before(asset_number, completed_at)

    if km is None:
        return ServiceInfo(
            km=0.0,
            work_order_number=wo_number(wo),
            completion_date=completed_at,
            status=wo_status(wo),
            reason="Completed oil WO found, but no odometer reading exists at/before completion date.",
        )

    return ServiceInfo(
        km=float(km),
        work_order_number=wo_number(wo),
        completion_date=completed_at,
        status=wo_status(wo),
        reason="Derived from latest odometer reading at/before completed oil WO date.",
    )


def has_open_oil_change_work_order_info(asset_number: str, asset_id: Any | None = None) -> OpenWorkOrderInfo:
    wos = get_work_orders_for_asset(asset_number, asset_id)

    for wo in wos:
        if not matches_oil_work_definition(wo):
            continue

        status = wo_status(wo)

        if is_canceled_status(status):
            continue

        if is_open_status(status):
            return OpenWorkOrderInfo(
                exists=True,
                work_order_number=wo_number(wo),
                status=status,
                reason="Open oil-change WO found, so script will not create duplicate.",
            )

    return OpenWorkOrderInfo(exists=False, reason="No open oil-change WO found.")


def get_debug_work_order_summaries(asset_number: str, asset_id: Any | None = None) -> list[dict]:
    return [wo_summary(wo) for wo in get_work_orders_for_asset(asset_number, asset_id)]


def fire_oil_change_event(asset_number: str) -> dict:
    """
    Fire condition-event action and let Oracle create the condition-based WO.

    Correct combination:
    - POST to parent resource: /maintenanceWorkOrders
    - Use wrapper body: {"name": "createConditionBasedWorkOrders", "parameters": [...]}
    - conditionCode must match the condition event attached to your requirement.
      Your GET showed EventCode = ZE2_OIL_CODE.
    """
    payload = {
        "name": "createConditionBasedWorkOrders",
        "parameters": [
            {"workOrderTypeCode": "CORRECTIVE"},
            {"workOrderSubTypeCode": "ORA_CONDITION_BASED"},
            {"assetNumber": asset_number},
            {"organizationCode": config.ORG_CODE},
            {"conditionCode": config.CONDITION_EVENT_CODE},
        ],
    }

    return _post_action(
        "maintenanceWorkOrders",
        payload,
        f"Firing oil-change condition event for {asset_number}",
    )
