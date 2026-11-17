from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from datetime import date, timedelta
from typing import Literal

import pandas as pd
import io

from routers.database import get_connection, get_aggregated_data, get_rows

router = APIRouter()


@router.get("/export")
def export_data(
    start_date: date,
    end_date: date,
    resolution: Literal["daily", "monthly", "yearly"],
    file_format: Literal["csv", "xlsx"],
):

    # --------------------------------------------------------
    # Validate date range
    # --------------------------------------------------------

    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")

    # End date is inclusive in the API.
    # SQL uses an exclusive upper boundary.
    start = start_date.isoformat()
    end = (end_date + timedelta(days=1)).isoformat()

    # --------------------------------------------------------
    # Map frontend resolution to database resolution
    # --------------------------------------------------------

    resolution_mapping = {
        "daily": "raw",
        "monthly": "daily",
        "yearly": "weekly",
    }

    db_resolution = resolution_mapping[resolution]

    # --------------------------------------------------------
    # Retrieve measurements for all devices
    # --------------------------------------------------------

    conn = get_connection()

    try:
        # Get devices available in the selected period
        device_rows = get_rows(conn, start, end)
        device_names = [row["device_name"] for row in device_rows]

        all_data = []

        for device_name in device_names:
            rows = get_aggregated_data(
                conn=conn,
                device_name=device_name,
                start=start,
                end=end,
                resolution=db_resolution
            )

            for row in rows:
                all_data.append({
                    "timestamp": row["timestamp"],
                    "device_name": device_name,
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "battery": row["battery"],
                })
    finally:
        conn.close()

    # --------------------------------------------------------
    # Create DataFrame
    # --------------------------------------------------------

    columns = [
        "timestamp",
        "device_name",
        "temperature",
        "humidity",
        "battery",
    ]

    df = pd.DataFrame(all_data, columns=columns)

    # --------------------------------------------------------
    # Adjust time column for export resolution
    # --------------------------------------------------------

    if resolution == "monthly":
        df.rename(columns={"timestamp": "date"}, inplace=True)

    elif resolution == "yearly":
        df.rename(columns={"timestamp": "week"}, inplace=True)

    # --------------------------------------------------------
    # Sort output chronologically and by device
    # --------------------------------------------------------

    time_column = df.columns[0]
    df.sort_values(by=[time_column, "device_name"], inplace=True)

    print(
        f"Export: {start_date} to {end_date}, "
        f"resolution={resolution}, "
        f"format={file_format}, "
        f"rows={len(df)}"
    )

    # --------------------------------------------------------
    # Export CSV
    # --------------------------------------------------------

    if file_format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    "attachment; filename=environment.csv"
            },
        )

    # --------------------------------------------------------
    # Export Excel
    # --------------------------------------------------------

    elif file_format == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Environment")
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition":
                    "attachment; filename=environment.xlsx"
            },
        )
