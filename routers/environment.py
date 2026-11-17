from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

from database import get_connection, get_aggregated_data, get_latest_two

from datetime import datetime, date, timedelta
import calendar

devices = [
    "Sensor 1 C122",
    "Sensor 2 C122",
    "Sensor 3 C122",
    "POIM001",
]

router = APIRouter()


# ============================================================
# MONTH
#
# One value per day.
# Missing days are returned with null values.
# ============================================================


@router.get("/month")
def get_month(
    device_name: str,
    year: int,
    month: int
):
    # --------------------------------------------------------
    # Define requested time interval
    # --------------------------------------------------------

    start_date = date(year, month, 1)

    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    # --------------------------------------------------------
    # Get daily averages from database
    # --------------------------------------------------------

    conn = get_connection()

    try:
        rows = get_aggregated_data(
            conn=conn,
            device_name=device_name,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            resolution="daily"
        )
    finally:
        conn.close()

    # --------------------------------------------------------
    # Convert database results into dictionary
    # --------------------------------------------------------

    database_data = {
        row["timestamp"]: {
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "battery": row["battery"],
        }
        for row in rows
    }

    # --------------------------------------------------------
    # Generate all days, including missing measurements
    # --------------------------------------------------------

    number_of_days = calendar.monthrange(
        year, month
    )[1]

    result = []

    for day in range(1, number_of_days + 1):

        current_date = date(year, month, day)
        date_string = current_date.isoformat()

        result.append({
            "date": date_string,
            **database_data.get(
                date_string,
                {
                    "temperature": None,
                    "humidity": None,
                    "battery": None
                }
            )
        })

    return result



# ============================================================
# YEAR
#
# One value per week.
# Monday is the start of the week.
#
# Missing weeks are returned with null values.
# ============================================================


@router.get("/year")
def get_year(
    device_name: str,
    year: int
):
    # --------------------------------------------------------
    # Define requested time interval
    # --------------------------------------------------------

    start_date = date(year, 1, 1)
    end_date = date(year + 1, 1, 1)

    # --------------------------------------------------------
    # Get weekly averages from database
    # --------------------------------------------------------

    conn = get_connection()

    try:
        rows = get_aggregated_data(
            conn=conn,
            device_name=device_name,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            resolution="weekly"
        )
    finally:
        conn.close()

    # --------------------------------------------------------
    # Convert database results into dictionary
    # --------------------------------------------------------

    database_data = {
        row["timestamp"]: {
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "battery": row["battery"],
        }
        for row in rows
    }

    # --------------------------------------------------------
    # Find first Monday of the year
    # --------------------------------------------------------

    first_day = date(year, 1, 1)

    days_until_monday = (
        7 - first_day.weekday()
    ) % 7

    first_monday = (
        first_day +
        timedelta(days=days_until_monday)
    )

    # --------------------------------------------------------
    # Generate all weeks, including missing measurements
    # --------------------------------------------------------

    result = []

    current_date = first_monday

    while current_date.year == year:

        date_string = current_date.isoformat()

        result.append({
            "date": date_string,
            **database_data.get(
                date_string,
                {
                    "temperature": None,
                    "humidity": None,
                    "battery": None
                }
            )
        })

        current_date += timedelta(days=7)

    return result



# ============================================================
# DAY
#
# One value every 30 minutes.
#
# Missing measurements are returned with null values.
# This means the x-axis always runs from 00:00 to 23:30.
# ============================================================


@router.get("/day")
def get_day(
    device_name: str,
    date: str
):
    # --------------------------------------------------------
    # Define requested time interval
    # --------------------------------------------------------

    requested_date = datetime.strptime(
        date, "%Y-%m-%d"
    ).date()

    start = datetime.combine(
        requested_date,
        datetime.min.time()
    )

    end = start + timedelta(days=1)

    # --------------------------------------------------------
    # Get raw measurements from database
    # --------------------------------------------------------

    conn = get_connection()

    try:
        rows = get_aggregated_data(
            conn=conn,
            device_name=device_name,
            start=start.isoformat(),
            end=end.isoformat(),
            resolution="raw"
        )
    finally:
        conn.close()

    # --------------------------------------------------------
    # Assign measurements to 30-minute intervals
    # --------------------------------------------------------

    database_data = {}

    for row in rows:

        timestamp = datetime.fromisoformat(
            row["timestamp"]
        )

        minute = 0 if timestamp.minute < 30 else 30

        normalized_timestamp = timestamp.replace(
            minute=minute,
            second=0,
            microsecond=0
        )

        database_data[normalized_timestamp.isoformat()] = {
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "battery": row["battery"],
        }

    # --------------------------------------------------------
    # Generate all 48 intervals, including missing values
    # --------------------------------------------------------

    result = []

    for i in range(48):

        timestamp = start + timedelta(minutes=30 * i)
        timestamp_string = timestamp.isoformat()

        result.append({
            "timestamp": timestamp_string,
            **database_data.get(
                timestamp_string,
                {
                    "temperature": None,
                    "humidity": None,
                    "battery": None
                }
            )
        })

    return result


@router.get("/latest")
def get_latest_measurement(device_name: str):
    return get_latest_two(device_name)


@router.websocket("/ws/latest")
async def websocket_latest(websocket: WebSocket):
    await websocket.accept()

    previous_state = None

    try:
        while True:
            current_state = {
                device: get_latest_two(device)
                for device in devices
            }

            if current_state != previous_state:
                await websocket.send_json(current_state)
                previous_state = current_state

            await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
