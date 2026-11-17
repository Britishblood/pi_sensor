import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_FILE = Path(
    "/home/poim/pi_sensor/data/20260810_environment.db"
)

@contextmanager
def get_connection():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=10
    )
    conn.row_factory = sqlite3.Row

    try:
        yield conn
    finally:
        conn.close()

def get_aggregated_data(
    conn,
    device_name,
    start,
    end,
    resolution
):
    time_groups = {
        "raw": "timestamp",
        "daily": "DATE(timestamp)",
        "weekly": """
            DATE(
                timestamp,
                '-' || (
                    (CAST(strftime('%w', timestamp) AS INTEGER) + 6) % 7
                ) || ' days'
            )
        """,
        "monthly": "strftime('%Y-%m-01', timestamp)",
        "yearly": "strftime('%Y-01-01', timestamp)"
    }

    group_expr = time_groups[resolution]

    query = f"""
        SELECT
            {group_expr} AS timestamp,
            AVG(va_temperature) AS temperature,
            AVG(va_humidity) AS humidity,
            AVG(battery_percentage) AS battery
        FROM environment
        WHERE device_name = ?
          AND timestamp >= ?
          AND timestamp < ?
        GROUP BY {group_expr}
        ORDER BY timestamp
    """

    return conn.execute(
        query,
        (device_name, start, end)
    ).fetchall()

def get_latest_two(device_name: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            timestamp,
            device_name,
            va_temperature,
            va_humidity,
            battery_percentage
        FROM environment
        WHERE device_name = ?
        ORDER BY timestamp DESC
        LIMIT 2
        """,
        (device_name,),
    )

    rows = cursor.fetchall()
    conn.close()

    if len(rows) == 0:
        return {
            "device_name": device_name,
            "timestamp": None,
            "temperature": None,
            "humidity": None,
            "battery": None,
            "previous_temperature": None,
            "previous_humidity": None,
        }

    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None

    return {
        "timestamp": latest[0],
        "device_name": latest[1],
        "temperature": latest[2],
        "humidity": latest[3],
        "battery": latest[4],
        "previous_temperature": previous[2] if previous else None,
        "previous_humidity": previous[3] if previous else None,
    }

def get_rows(conn, start, end):
    return conn.execute(
        """
        SELECT DISTINCT device_name
        FROM environment
        WHERE timestamp >= ?
          AND timestamp
            < ?
        ORDER BY device_name
        """,
        (start, end)
    ).fetchall()