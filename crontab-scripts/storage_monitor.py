import json
import shutil
import smtplib
from pathlib import Path
from email.message import EmailMessage
from env import USERNAME, PASSWORD, LIST_OF_RECEIVERS

# Configuration
DISK_PATH = "/"
THRESHOLD = 90
RESET_THRESHOLD = 85

SMTP_SERVER = "smtp.web.de"
SMTP_PORT = 465

SENDER_EMAIL = USERNAME
SENDER_PASSWORD = PASSWORD
RECEIVER_EMAIL = LIST_OF_RECEIVERS

STATE_FILE = Path.home() / ".storage_monitor_state.json"

TEST = False

def get_disk_usage():
    total, used, free = shutil.disk_usage(DISK_PATH)
    return used / total * 100, free / (1024**3)


def send_email(usage, free_gb):
    msg = EmailMessage()
    msg["Subject"] = "WARNING: Raspberry Pi (Temperature&Humidity-Sensor Tracker) storage almost full"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ",".join(RECEIVER_EMAIL)

    msg.set_content(
        f"Raspberry Pi storage warning!\n\n"
        f"Disk usage: {usage:.1f}%\n"
        f"Free storage: {free_gb:.2f} GB\n\n"
        f"Please transfer or delete files."
    )

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)


def check_storage():
    usage, free_gb = get_disk_usage()

    print(f"Disk usage: {usage:.1f}%")

    # Read previous alert state
    try:
        state = json.loads(STATE_FILE.read_text())
        alert_sent = state.get("alert_sent", False)
    except (FileNotFoundError, ValueError):
        alert_sent = False

    if usage >= THRESHOLD and not alert_sent:
        send_email(usage, free_gb)
        STATE_FILE.write_text(json.dumps({"alert_sent": True}))
        print("Warning email sent!")

    elif usage < RESET_THRESHOLD and alert_sent:
        STATE_FILE.write_text(json.dumps({"alert_sent": False}))
        print("Storage warning reset.")

    if TEST:
        send_email(usage, free_gb)
        STATE_FILE.write_text(json.dumps({"alert_sent": True}))
        print("Warning email sent!")



if __name__ == "__main__":
    check_storage()
