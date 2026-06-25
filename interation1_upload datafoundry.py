import serial
import requests
import json
import time


# SERIAL SETTINGS


SERIAL_PORT = "COM3"
BAUD_RATE = 115200


# DATAFOUNDRY SETTINGS, changed the datafoundry token per participant so every participant had to run their own script


DATAFOUNDRY_TOKEN = "bldVaDVLMzBkVHI2V3VtR1pwak5URzIyWjBtSkhqWnA2OGtrb3M2Sm5CYz0="
DATASET_ID = "20872"

DATAFOUNDRY_URL = (
    "https://datafoundry.id.tue.nl/api/v1/datasets/ts/"
    + DATASET_ID
    + "/"
    + DATAFOUNDRY_TOKEN
)

SOURCE_ID = "sparkfun_esp32_usb"
ACTIVITY = "buttons_potentiometer_usb"


# OPEN SERIAL PORT


print("Opening serial port", SERIAL_PORT)

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
time.sleep(2)

print("Reading data from ESP32 on COM3...")
print("Uploading to DataFoundry dataset", DATASET_ID)
print("Press Ctrl+C to stop.")
print()


# MAIN LOOP


while True:
    try:
        line = ser.readline().decode("utf-8", errors="ignore").strip()

        if not line:
            continue

        print("Received from ESP32:")
        print(line)

        data = json.loads(line)

        jsondata = {
            "source_id": SOURCE_ID,
            "activity": ACTIVITY,
            "data": json.dumps(data)
        }

        response = requests.post(DATAFOUNDRY_URL, json=jsondata)

        print("DataFoundry status:", response.status_code)
        print("DataFoundry response:", response.text)
        print("-" * 40)

    except json.JSONDecodeError:
        print("Invalid JSON from ESP32:")
        print(line)
        print("-" * 40)

    except KeyboardInterrupt:
        print("Stopped by user.")
        ser.close()
        break

    except Exception as e:
        print("Error:", e)
        time.sleep(2)