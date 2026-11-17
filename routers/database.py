import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
import csv

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DB_FILE = DATA_DIR / "20260810_environment.db"

@contextmanager
def get_connection():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=10
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def initialize_database():
    """
    Initialize the SQLite database.

    Creates:
        - Database directory
        - SQLite database file
        - environment table
        - Index for device/timestamp queries

    Existing data is preserved.
    """

    # Create database directory if necessary
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        # Enable WAL for concurrent reading/writing
        conn.execute("PRAGMA journal_mode=WAL")

        # Create environment table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS environment (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                timestamp TEXT NOT NULL,
                device_name TEXT NOT NULL,

                va_temperature REAL,
                va_humidity REAL,
                battery_percentage REAL,

                UNIQUE(device_name, timestamp)
            )
        """)

        # Improve lookup and aggregation performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_environment_device_timestamp
            ON environment(device_name, timestamp)
        """)

    print(f"Database initialized: {DB_FILE}")


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
    with get_connection() as conn:
        rows = conn.execute(
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
            (device_name,)
        ).fetchall()


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
        "timestamp": latest["timestamp"],
        "device_name": latest["device_name"],
        "temperature": latest["va_temperature"],
        "humidity": latest["va_humidity"],
        "battery": latest["battery_percentage"],
        "previous_temperature": (previous["va_temperature"] if previous else None),
        "previous_humidity": (previous["va_humidity"] if previous else None),
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



def recover_database_from_csv(csv_files: list[str | Path]) -> dict:
    """
    Recover missing measurements from multiple CSV files.

    Parameters
    ----------
    csv_files : list[str | Path]
        List of CSV filenames or paths.

        Relative paths are resolved against DATA_DIR.

    Returns
    -------
    dict
        Recovery summary with per-file statistics.

    Notes
    -----
    - Database must already exist and be initialized.
    - Existing measurements are not overwritten.
    - Duplicate device/timestamp pairs are skipped.
    - All files are imported in a single transaction.
    """

    # --------------------------------------------------------
    # Check database
    # --------------------------------------------------------

    if not DB_FILE.is_file():
        raise FileNotFoundError(f"Database not found: {DB_FILE}. Run initialize_database() manually first.")

    # --------------------------------------------------------
    # Resolve and validate CSV paths
    # --------------------------------------------------------

    paths = []

    for csv_file in csv_files:
        path = Path(csv_file)
        if not path.is_absolute():
            path = DATA_DIR / path
        if not path.is_file():
            raise FileNotFoundError(f"CSV file not found: {path}")

        paths.append(path)

    # --------------------------------------------------------
    # CSV column mapping
    # --------------------------------------------------------

    column_aliases = {
        "timestamp": "timestamp",
        "device_name": "device_name",
        "va_temperature": "va_temperature",
        "temperature": "va_temperature",
        "va_humidity": "va_humidity",
        "humidity": "va_humidity",
        "battery_percentage": "battery_percentage",
        "battery": "battery_percentage",
    }

    required_columns = {
        "timestamp",
        "device_name",
        "va_temperature",
        "va_humidity",
        "battery_percentage",
    }

    def parse_number(value):
        if value is None or not str(value).strip():
            return None
        return float(value)

    # --------------------------------------------------------
    # Import measurements
    # --------------------------------------------------------

    summary = {
        "total": 0,
        "imported": 0,
        "skipped": 0,
        "files": {}
    }

    with get_connection() as conn:

        # Verify required table exists
        table_exists = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'environment'
            """
        ).fetchone()

        if not table_exists:
            raise RuntimeError("Table 'environment' does not exist. Run initialize_database() manually.")

        for path in paths:
            file_total = 0
            file_imported = 0
            file_skipped = 0

            with path.open("r", encoding="utf-8-sig", newline="") as file:

                reader = csv.DictReader(file)

                if reader.fieldnames is None:
                    raise ValueError(f"CSV is empty: {path}")

                # Map CSV headers to DB column names
                headers = {
                    column_aliases[name.strip()]: name
                    for name in reader.fieldnames
                    if name and name.strip() in column_aliases
                }

                missing = required_columns - set(headers)

                if missing:
                    raise ValueError(f"Missing columns in {path.name}: {sorted(missing)}")

                for row_number, row in enumerate(reader, start=2):

                    if None in row:
                        raise ValueError(f"Malformed row {row_number} in {path.name}")

                    # Ignore completely empty rows
                    if not any(value and str(value).strip() for value in row.values()):
                        continue

                    file_total += 1

                    # Normalize timestamp
                    timestamp = datetime.fromisoformat(row[headers["timestamp"]].strip()).isoformat()
                    device_name = (row[headers["device_name"]].strip())
                    if not device_name:
                        raise ValueError(
                            f"Missing device name in "
                            f"{path.name}, row {row_number}"
                        )
                    temperature = parse_number(row[headers["va_temperature"]])
                    humidity = parse_number(row[headers["va_humidity"]])
                    battery = parse_number(row[headers["battery_percentage"]])

                    # Only insert if device/timestamp is absent
                    cursor = conn.execute(
                        """
                        INSERT INTO environment (
                            timestamp,
                            device_name,
                            va_temperature,
                            va_humidity,
                            battery_percentage
                        )
                        SELECT ?, ?, ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM environment
                            WHERE device_name = ?
                              AND timestamp = ?
                        )
                        """,
                        (
                            timestamp,
                            device_name,
                            temperature,
                            humidity,
                            battery,
                            device_name,
                            timestamp,
                        )
                    )
                    if cursor.rowcount == 1:
                        file_imported += 1
                    else:
                        file_skipped += 1

            # ------------------------------------------------
            # Per-file summary
            # ------------------------------------------------

            summary["files"][str(path)] = {
                "total": file_total,
                "imported": file_imported,
                "skipped": file_skipped,
            }

            summary["total"] += file_total
            summary["imported"] += file_imported
            summary["skipped"] += file_skipped

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    print("\nDatabase recovery completed.")
    print(f"CSV files: {len(paths)}")
    print(f"Total rows: {summary['total']}")
    print(f"Imported:   {summary['imported']}")
    print(f"Skipped:    {summary['skipped']}")

    for filename, stats in summary["files"].items():
        print(f"\n{Path(filename).name}")
        print(f"  Total:    {stats['total']}")
        print(f"  Imported: {stats['imported']}")
        print(f"  Skipped:  {stats['skipped']}")

    return summary
