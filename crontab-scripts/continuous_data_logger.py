import logging
import os
from datetime import datetime
from env import ENDPOINT, ACCESS_ID, ACCESS_KEY, USERNAME, PASSWORD
from tuya_iot import TuyaOpenAPI, TUYA_LOGGER
import pandas as pd
import sqlite3

# Enable logging
TUYA_LOGGER.setLevel(logging.ERROR)  # set to DEBUG if you want more logs

# Init API
openapi = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)
openapi.connect(USERNAME, PASSWORD, "49", "smartlife")

uid = openapi.token_info.uid
print("Connected as UID:", uid)
csv_file = "/home/poim/pi_sensor/data/tuya_devices_current.csv"
db_file = "/home/poim/pi_sensor/data/20260810_environment.db"

try:
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Get devices
    devices = openapi.get(f"/v1.0/users/{uid}/devices").get("result", [])
    rows = []
        
    for d in devices:
        dev_id = d["id"]
        dev_name = d["name"]
        
        # Fetch status datapoints
        status = openapi.get(f"/v1.0/devices/{dev_id}/status").get("result", [])
        
        # Build a dictionary with default None values
        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": dev_id,
            "device_name": dev_name,
            "va_temperature": None,
            "va_humidity": None,
            "battery_percentage": None
        }
        
        # Fill in the values from status
        for item in status:
            if item["code"] in ["va_temperature", "va_humidity", "battery_percentage"]:
                record[item["code"]] = item["value"]
        
        rows.append(record)
        
    # Save if we collected data
    if rows:
        df = pd.DataFrame(rows)

        # -------------------------
        # Save to CSV
        # -------------------------
        file_exists = os.path.isfile(csv_file)
        df.to_csv(csv_file, mode='a', header=not file_exists, index=False)
        print(f"Logged {len(rows)} entries to {csv_file}")


        # -----------------------
        # Save to SQLite
        # -------------------------
        with sqlite3.connect(db_file) as conn:
            df.to_sql(
                "environment",
                conn,
                if_exists="append",
                index=False,
            )

        print(f"Added {len(rows)} entries to {db_file}")

except Exception as e:
    print("Error:", e)
