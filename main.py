"""
main.py
=======
Fleet Oil Change Monitor.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import logging
import sys

import requests

import config
import logic
import oracle_api


def _setup_logging() -> logging.Logger:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    log_folder = Path(__file__).parent / "logs"
    log_folder.mkdir(exist_ok=True)
    log_filename = log_folder / f"oil_change_{datetime.now().strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("fleet_oil_change")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_filename, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.log_filename = str(log_filename)  # type: ignore[attr-defined]
    return logger


log = _setup_logging()


def run() -> None:
    sep = "=" * 75
    log.info(sep)
    log.info("FLEET OIL CHANGE MONITOR")
    log.info("Run started at       : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Organization         : %s", config.ORG_CODE)
    log.info("Item filter          : %s", config.ITEM_NUMBER)
    log.info("Meter                : %s", config.METER_CODE)
    log.info("Condition event code : %s", config.CONDITION_EVENT_CODE)
    log.info("Service interval KM  : %s", f"{config.OIL_CHANGE_INTERVAL_KM:,}")
    log.info("Dry run              : %s", config.DRY_RUN)
    log.info("Debug work orders    : %s", config.DEBUG_WORK_ORDERS)
    log.info(sep)

    counters = {
        "total": 0,
        "no_reading": 0,
        "ok": 0,
        "due": 0,
        "already_open": 0,
        "created": 0,
        "would_create": 0,
        "errors": 0,
    }

    try:
        cars = oracle_api.get_all_cars()
    except requests.HTTPError as exc:
        log.error("FATAL: Could not fetch cars.")
        log.error(str(exc))
        sys.exit(1)

    log.info("Found %s car(s).", len(cars))

    for car in cars:
        asset_number = str(car.get("AssetNumber", "UNKNOWN"))
        asset_id = car.get("AssetId")
        counters["total"] += 1

        log.info("")
        log.info("-" * 75)
        log.info("Car asset number: %s | AssetId: %s", asset_number, asset_id)

        try:
            if config.DEBUG_WORK_ORDERS:
                summaries = oracle_api.get_debug_work_order_summaries(asset_number, asset_id)
                log.info("  DEBUG: Work orders found for asset: %s", len(summaries))
                for s in summaries:
                    log.info(
                        "  DEBUG WO: number=%s | status=%s | workdef=%s | completion=%s | desc=%s",
                        s.get("WorkOrderNumber"),
                        s.get("Status"),
                        s.get("WorkDefinition"),
                        s.get("CompletionDate"),
                        s.get("Description"),
                    )

            current_km = oracle_api.get_latest_odometer_reading(asset_number)
            if current_km is None:
                log.warning("  Current odometer : NO READING FOUND. Skipping.")
                counters["no_reading"] += 1
                continue

            log.info("  Current odometer : %s KM", f"{current_km:,.0f}")

            service = oracle_api.get_last_completed_oil_change_info(asset_number, asset_id)
            last_service_km = service.km

            if service.work_order_number:
                log.info(
                    "  Last oil service : %s KM | WO=%s | Status=%s | Completed=%s",
                    f"{last_service_km:,.0f}",
                    service.work_order_number,
                    service.status,
                    service.completion_date,
                )
                log.info("  Service source   : %s", service.reason)
            else:
                log.info("  Last oil service : 0 KM | %s", service.reason)

            km_since_service = logic.calculate_km_since_last_service(current_km, last_service_km)
            remaining = logic.remaining_km(km_since_service)

            log.info("  Since service    : %s KM", f"{km_since_service:,.0f}")
            if remaining > 0:
                log.info("  Remaining        : %s KM", f"{remaining:,.0f}")
            else:
                log.info("  Remaining        : OVERDUE by %s KM", f"{abs(remaining):,.0f}")

            if not logic.is_oil_change_due(km_since_service):
                log.info("  Status           : OK - no service needed")
                counters["ok"] += 1
                continue

            counters["due"] += 1
            log.info("  Status           : SERVICE DUE")

            open_wo = oracle_api.has_open_oil_change_work_order_info(asset_number, asset_id)
            if open_wo.exists:
                log.info(
                    "  Action           : Existing open oil WO found. No duplicate created. WO=%s | Status=%s",
                    open_wo.work_order_number,
                    open_wo.status,
                )
                counters["already_open"] += 1
                continue

            if config.DRY_RUN:
                log.info("  Action           : DRY_RUN=true, would fire condition event now.")
                counters["would_create"] += 1
                continue

            log.info("  Action           : No open WO found. Firing condition event...")
            result = oracle_api.fire_oil_change_event(asset_number)
            log.info("  Result           : Condition event sent successfully.")
            log.info("  Oracle response  : %s", result)
            counters["created"] += 1

        except requests.HTTPError as exc:
            counters["errors"] += 1
            log.error("  API ERROR for %s", asset_number)
            log.error(str(exc))

        except Exception as exc:
            counters["errors"] += 1
            log.exception("  UNEXPECTED ERROR for %s: %s", asset_number, exc)

    log.info("")
    log.info(sep)
    log.info("SUMMARY REPORT")
    log.info(sep)
    log.info("Total cars checked          : %s", counters["total"])
    log.info("Cars with no meter reading  : %s", counters["no_reading"])
    log.info("Cars OK                     : %s", counters["ok"])
    log.info("Cars due for service        : %s", counters["due"])
    log.info("Already had open WO         : %s", counters["already_open"])
    log.info("Would create, dry run only  : %s", counters["would_create"])
    log.info("Work orders/events created  : %s", counters["created"])
    log.info("Cars with errors            : %s", counters["errors"])
    log.info("Log saved to                : %s", getattr(log, "log_filename", "logs folder"))
    log.info(sep)

    if counters["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    run()
