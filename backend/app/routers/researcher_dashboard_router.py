"""
File: researcher_dashboard_router.py

Purpose:
Handles all HTTP endpoints for the researcher dashboard, providing
filtered access to sensor data, trend charts, status summaries,
CSV export, and alert history.

Responsibilities:
- Return a dashboard summary with latest values for the top cards
  and warning banner on the researcher overview page
- Return historical trend data for the researcher charts, with
  optional filters for site and date range
- Return status counts (normal, warning, critical) across all readings
- Return filtered sensor data for the researcher data tables page
- Stream filtered sensor data as a downloadable CSV file for export
- Return alert history from the alert_log table with optional filters
  for site, date range, and severity level
- Validate filter inputs including date format and allowed status
  and severity values before passing them to the repository

Layer:
Backend (Router / API)

Related:
- sensor_reading_repository.py (all sensor data queries)
- alert_log_repository.py (alert history queries)
- schemas/sensor_reading.py (response models for data and trends)
- schemas/alert_log.py (response model for alert history)
- researcher.js (frontend charts, filters, and data tables)
- alerts.js (frontend alert history view)
- main.py (registers this router with the FastAPI app)

Reference:
some ideas were taking from here https://youtu.be/3-s95QV2DFw?si=NPeJ5CzYMne9e3s7, how to start building the backend
for the dasboard. 
chatgpt, Claude AI were also used to explain the errors, and helped us also understand some parts of the youtube video 
provieded above 
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.sensor_reading_repository import (
    get_dashboard_summary,
    get_trend_data,
    get_status_counts,
)

from app.repositories.sensor_reading_repository import (
    get_dashboard_summary,
    get_trend_data,
    get_status_counts,
    get_researcher_data,
    get_researcher_data_for_export,
    get_alert_history,
)

from app.schemas.sensor_reading import ResearcherDataResponse, AlertHistoryResponse

from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime

from app.repositories.alert_log_repository import get_alert_history
from app.schemas.alert_log import AlertLogResponse

router = APIRouter(prefix="/api/researcher/dashboard", tags=["researcher-dashboard"])

def validate_filters(
    start_date: str | None,
    end_date: str | None,
    status: str | None,
):
    # allowed status values for filtering
    allowed_statuses = {"normal", "warning", "critical"}

    if status and status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="invalid status. allowed values: normal, warning, critical",
        )

    # check if dates are valid strings in datetime format
    try:
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="invalid date format. use YYYY-MM-DD HH:MM:SS",
        )

@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """
    returns latest values for top cards and warning banner
    """
    return get_dashboard_summary(db)


@router.get("/trends")
def trends(
    site_id: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
):
    """
    returns historical data for graphs
    """
    return get_trend_data(db, site_id, start_date, end_date, limit)


@router.get("/status-counts")
def status_counts(db: Session = Depends(get_db)):
    """
    returns number of normal, warning, critical readings
    """
    return get_status_counts(db)


@router.get(
    "/data",
    response_model=list[ResearcherDataResponse],
)
@router.get(
    "/data",
    response_model=list[ResearcherDataResponse],
)
def researcher_data(
    site_id: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=5000),
    db: Session = Depends(get_db),
):
    """
    returns filtered data for the researcher data page table
    """

    # treat "all" or empty string as "no filter"
    if site_id in ("all", ""):
        site_id = None
    if status in ("all", ""):
        status = None

    validate_filters(start_date, end_date, status)

    return get_researcher_data(
        db=db,
        site_id=site_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        limit=limit,
    )

@router.get("/data/export")
def export_researcher_data(
    site_id: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    exports filtered researcher data as csv
    """
    # treat "all" or empty string as "no filter"
    if site_id in ("all", ""):
        site_id = None
    if status in ("all", ""):
        status = None

    validate_filters(start_date, end_date, status)
    readings = get_researcher_data_for_export(
        db=db,
        site_id=site_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "site_id",
        "timestamp",
        "air_temperature_c",
        "relative_humidity_pct",
        "leaf_wetness_0_1",
        "pest_trap_count",
        "wx_rain_mm_hr",
        "status",
        "alert_triggered",
        "alert_pest_action",
        "alert_pest_outbreak",
        "alert_disease_moderate",
        "alert_disease_high",
    ])
    # loop through each database row and write it into csv
    for r in readings:
        writer.writerow([
            r.site_id,
            r.timestamp,
            r.air_temperature_c,
            r.relative_humidity_pct,
            r.leaf_wetness_0_1,
            r.pest_trap_count,
            r.wx_rain_mm_hr,
            r.status,
            r.alert_triggered,
            r.alert_pest_action,
            r.alert_pest_outbreak,
            r.alert_disease_moderate,
            r.alert_disease_high,
        ])
    # move cursor back to the beginning of the file before sending it
    output.seek(0)
    # return the csv as a downloadable file
    # streamingresponse is used so the file is sent directly to the user
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=researcher_data.csv"},
    )

@router.get(
    "/alerts/history",
    response_model=list[AlertLogResponse],
)
def alert_history(
    site_id: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """
    returns alert history from alert_log table
    """

    allowed_severity = {"warning", "critical"}
    if severity and severity not in allowed_severity:
        raise HTTPException(
            status_code=400,
            detail="invalid severity. allowed values: warning, critical",
        )

    return get_alert_history(
        db=db,
        site_id=site_id,
        start_date=start_date,
        end_date=end_date,
        severity=severity,
        limit=limit,
    )