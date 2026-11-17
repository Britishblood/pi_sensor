import pandas as pd
from webdav3.client import Client
from datetime import datetime
from env import USERNAME_BW, PASSWORD_BW, REMOTE_PATH
import shutil
import os



options = {
    "webdav_hostname": "https://bwsyncandshare.kit.edu/remote.php/webdav/",  
    "webdav_login":    USERNAME_BW,            
    "webdav_password": PASSWORD_BW  
}

try:
    client = Client(options)

    total, used, free = shutil.disk_usage('/')
    gigabytes = free / (2**30)
    if gigabytes < 1.0:
        # Create notification file
        notif_file = "LOW_DISK_SPACE.txt"
        with open(notif_file, "w") as f:
            f.write("LOW_DISK_SPACE")
        # Optionally upload the notification
        client.upload_sync(
            local_path=notif_file,
            remote_path=f"{REMOTE_PATH}{notif_file}"
        )
        print("Low disk space notification sent!")

    local_file = "/home/poim/pi_sensor/data/tuya_devices_current.csv"
    # --- Check battery levels in current CSV ---
    if os.path.isfile(local_file):
        df = pd.read_csv(local_file)
        low_battery_devices = df[df['battery_percentage'] < 10]
        
        if not low_battery_devices.empty:
            # Send a notification file
            notif_file = "/home/poim/pi_sensor/data/LOW_BATTERY.txt"
            with open(notif_file, "w") as f:
                for dev_name in low_battery_devices['device_name'].unique():
                    f.write(f"{dev_name}\n")
            client.upload_sync(
                local_path=notif_file,
                remote_path=f"{REMOTE_PATH}{notif_file}"
            )
            print("Low battery notification sent!")       
    
    
        today_str = datetime.now().strftime("%Y-%m-%d")
        remote_path = f"{REMOTE_PATH}tuya_devices_{today_str}.csv"
        
        # Upload local file into that folder
        client.upload_sync(
            remote_path=remote_path,
            local_path=local_file
        )
        
        # Renaming current to date
        os.rename("/home/poim/pi_sensor/data/tuya_devices_current.csv", f'/home/poim/pi_sensor/data/tuya_devices_{today_str}.csv')
        
except Exception as e:
    print("Error:", e)