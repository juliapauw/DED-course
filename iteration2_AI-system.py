import csv
import json
import os
import threading

from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    request,
    send_file
)

from google import genai
from google.genai import types


# SERVER, GEMINI AND CSV SETUP

app = Flask(__name__)

api_key = os.environ.get(
    "GEMINI_API_KEY"
)

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. "
        "Set the API key in Terminal before starting the server."
    )

client = genai.Client(
    api_key=api_key
)

GEMINI_MODEL = "gemini-2.5-flash"

# The CSV is created next to this script in:
# data/interaction_log.csv
BASE_DIR = Path(
    __file__
).resolve().parent

DATA_DIR = BASE_DIR / "data"

CSV_PATH = (
    DATA_DIR
    / "interaction_log.csv"
)

csv_lock = threading.Lock()



# CSV COLUMNS


CSV_COLUMNS = [
    "server_timestamp_local",
    "server_timestamp_utc",

    "event_type",
    "event_id",
    "session_id",
    "measurement_id",
    "device_id",
    "device_uptime_ms",
    "source_message_type",

    # Phone-case measurements
    "phone_duration_s",
    "duration_minutes",
    "button_presses",
    "button_presses_per_minute",
    "button1_pressed",
    "button2_pressed",
    "pot_raw",
    "pot_delta",
    "pot_activity",
    "pot_activity_per_minute",
    "accelerometer_x",
    "accelerometer_y",
    "accelerometer_z",
    "motion_value",
    "motion_seconds",
    "motion_seconds_per_minute",
    "total_motion_amount",
    "max_static_s",
    "current_static_s",
    "total_static_s",
    "engagement_detected",
    "behavior",
    "behavior_reason",
    "pet_status",
    "intervention_active",

    # Human-readable phone and buzzer output
    "phone_serial_text",
    "phone_status_sent_text",
    "buzzer_received_raw_json",
    "buzzer_received_json",
    "buzzer_status_text",

    # Buzzer and virtual-pet reaction
    "buzzer_alarm_active",
    "buzzer_face",
    "lcd_line_1",
    "lcd_line_2",
    "alarm_step",
    "buzzer1_frequency_hz",
    "buzzer2_frequency_hz",
    "red_button_pressed",
    "reaction_time_s",
    "reset_packets_sent",

    # Gemini input and response
    "ai_input_json",
    "ai_behavior",
    "ai_status",
    "ai_model",
    "gemini_quote",
    "fallback",
    "error",

    # Complete original JSON as backup
    "raw_payload_json"
]

# CSV HELPERS

def current_local_timestamp():
    return (
        datetime.now()
        .astimezone()
        .isoformat(
            timespec="milliseconds"
        )
    )


def current_utc_timestamp():
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="milliseconds"
        )
    )


def create_csv_if_needed():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if (
        CSV_PATH.exists()
        and CSV_PATH.stat().st_size > 0
    ):
        try:
            with CSV_PATH.open(
                "r",
                newline="",
                encoding="utf-8-sig"
            ) as csv_file:
                existing_header = next(
                    csv.reader(csv_file),
                    []
                )

            if existing_header == CSV_COLUMNS:
                return

            backup_name = (
                "interaction_log_previous_"
                + datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
                + ".csv"
            )

            backup_path = (
                DATA_DIR / backup_name
            )

            CSV_PATH.replace(
                backup_path
            )

            print(
                "Previous CSV schema backed up to:",
                backup_path
            )

        except Exception as error:
            print(
                "Could not inspect previous CSV header:",
                error
            )

            return

    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_COLUMNS
        )

        writer.writeheader()

def first_value(
    payload,
    *names,
    default=""
):
    for name in names:
        if name in payload:
            return payload[name]

    return default


def csv_value(value):
    if value is None:
        return ""

    if isinstance(
        value,
        bool
    ):
        return int(value)

    if isinstance(
        value,
        (dict, list, tuple)
    ):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":")
        )

    return value


def normalize_csv_row(
    payload,
    default_event_type
):
    row = {
        column: ""
        for column in CSV_COLUMNS
    }

    event_type = first_value(
        payload,
        "event_type",
        "ev",
        default=default_event_type
    )

    source_message_type = first_value(
        payload,
        "source_message_type",
        "src",
        "type"
    )

    duration = first_value(
        payload,
        "phone_duration_s",
        "duration",
        "d",
        default=0
    )

    button_presses = first_value(
        payload,
        "button_presses",
        "btns",
        "b",
        default=0
    )

    pot_raw = first_value(
        payload,
        "pot_raw",
        "pr"
    )

    pot_activity = first_value(
        payload,
        "pot_activity",
        "pa",
        "wheel",
        default=0
    )

    motion_value = first_value(
        payload,
        "motion_value",
        "motion",
        "m"
    )

    motion_seconds = first_value(
        payload,
        "motion_seconds",
        "ms",
        default=0
    )

    max_static = first_value(
        payload,
        "max_static_s",
        "max_static",
        "mx",
        default=0
    )

    current_static = first_value(
        payload,
        "current_static_s",
        "current_static",
        "cs",
        default=0
    )

    total_static = first_value(
        payload,
        "total_static_s",
        "total_static",
        "ts",
        default=0
    )

    engagement = first_value(
        payload,
        "engagement_detected",
        "e",
        default=0
    )

    behavior = str(
        first_value(
            payload,
            "behavior",
            "bh",
            default="UNKNOWN"
        )
    ).upper()

    pet_status = str(
        first_value(
            payload,
            "pet_status",
            "ps",
            default="UNKNOWN"
        )
    ).upper()

    try:
        duration_number = float(
            duration
        )
    except Exception:
        duration_number = 0.0

    duration_minutes = round(
        duration_number / 60.0,
        2
    )

    rate_minutes = duration_minutes

    if rate_minutes < 1.0:
        rate_minutes = 1.0

    try:
        button_rate = round(
            float(button_presses) / rate_minutes,
            2
        )
    except Exception:
        button_rate = 0.0

    try:
        pot_rate = round(
            float(pot_activity) / rate_minutes,
            2
        )
    except Exception:
        pot_rate = 0.0

    try:
        motion_rate = round(
            float(motion_seconds) / rate_minutes,
            2
        )
    except Exception:
        motion_rate = 0.0

    phone_serial_text = first_value(
        payload,
        "phone_serial_text"
    )

    if not phone_serial_text:
        phone_serial_text = (
            "Time: {} sec | Buttons: {} | Pot raw: {} | "
            "Pot activity: {} | Motion: {} | Motion sec: {} | "
            "Still now: {} | Total still: {} | Engagement: {} | "
            "Behavior: {} | Pet: {}"
        ).format(
            duration,
            button_presses,
            pot_raw,
            pot_activity,
            motion_value,
            motion_seconds,
            current_static,
            total_static,
            engagement,
            behavior,
            pet_status
        )

    phone_status_sent_text = first_value(
        payload,
        "phone_status_sent_text"
    )

    if not phone_status_sent_text:
        phone_status_sent_text = (
            "{} sent: {} | {}"
        ).format(
            source_message_type or event_type,
            pet_status,
            behavior
        )

    buzzer_status_text = first_value(
        payload,
        "buzzer_status_text"
    )

    if not buzzer_status_text:
        buzzer_status_text = (
            "{}: {} | behavior: {}"
        ).format(
            source_message_type or event_type,
            pet_status,
            behavior
        )

    row.update({
        "server_timestamp_local": (
            current_local_timestamp()
        ),
        "server_timestamp_utc": (
            current_utc_timestamp()
        ),
        "event_type": event_type,
        "event_id": first_value(
            payload,
            "event_id",
            "eid"
        ),
        "session_id": first_value(
            payload,
            "session_id",
            "sid"
        ),
        "measurement_id": first_value(
            payload,
            "measurement_id",
            "mid"
        ),
        "device_id": first_value(
            payload,
            "device_id",
            "dev",
            default="UNKNOWN"
        ),
        "device_uptime_ms": first_value(
            payload,
            "device_uptime_ms",
            "up"
        ),
        "source_message_type": source_message_type,
        "phone_duration_s": duration,
        "duration_minutes": duration_minutes,
        "button_presses": button_presses,
        "button_presses_per_minute": button_rate,
        "button1_pressed": first_value(
            payload,
            "button1_pressed"
        ),
        "button2_pressed": first_value(
            payload,
            "button2_pressed"
        ),
        "pot_raw": pot_raw,
        "pot_delta": first_value(
            payload,
            "pot_delta"
        ),
        "pot_activity": pot_activity,
        "pot_activity_per_minute": pot_rate,
        "accelerometer_x": first_value(
            payload,
            "accelerometer_x",
            "ax"
        ),
        "accelerometer_y": first_value(
            payload,
            "accelerometer_y",
            "ay"
        ),
        "accelerometer_z": first_value(
            payload,
            "accelerometer_z",
            "az"
        ),
        "motion_value": motion_value,
        "motion_seconds": motion_seconds,
        "motion_seconds_per_minute": motion_rate,
        "total_motion_amount": first_value(
            payload,
            "total_motion_amount"
        ),
        "max_static_s": max_static,
        "current_static_s": current_static,
        "total_static_s": total_static,
        "engagement_detected": engagement,
        "behavior": behavior,
        "behavior_reason": first_value(
            payload,
            "behavior_reason"
        ),
        "pet_status": pet_status,
        "intervention_active": first_value(
            payload,
            "intervention_active"
        ),
        "phone_serial_text": phone_serial_text,
        "phone_status_sent_text": phone_status_sent_text,
        "buzzer_received_raw_json": first_value(
            payload,
            "buzzer_received_raw_json"
        ),
        "buzzer_received_json": first_value(
            payload,
            "buzzer_received_json"
        ),
        "buzzer_status_text": buzzer_status_text,
        "buzzer_alarm_active": first_value(
            payload,
            "buzzer_alarm_active",
            "ba"
        ),
        "buzzer_face": first_value(
            payload,
            "buzzer_face",
            "face"
        ),
        "lcd_line_1": first_value(
            payload,
            "lcd_line_1",
            "l1"
        ),
        "lcd_line_2": first_value(
            payload,
            "lcd_line_2",
            "l2"
        ),
        "alarm_step": first_value(
            payload,
            "alarm_step",
            "step"
        ),
        "buzzer1_frequency_hz": first_value(
            payload,
            "buzzer1_frequency_hz"
        ),
        "buzzer2_frequency_hz": first_value(
            payload,
            "buzzer2_frequency_hz"
        ),
        "red_button_pressed": first_value(
            payload,
            "red_button_pressed",
            "rb"
        ),
        "reaction_time_s": first_value(
            payload,
            "reaction_time_s",
            "reaction_time",
            "rt"
        ),
        "reset_packets_sent": first_value(
            payload,
            "reset_packets_sent",
            "reset_count"
        ),
        "ai_input_json": first_value(
            payload,
            "ai_input_json"
        ),
        "ai_behavior": first_value(
            payload,
            "ai_behavior",
            "behavior",
            "bh",
            default=behavior
        ),
        "ai_status": first_value(
            payload,
            "ai_status"
        ),
        "ai_model": first_value(
            payload,
            "ai_model"
        ),
        "gemini_quote": first_value(
            payload,
            "gemini_quote",
            "ai_quote",
            "quote",
            "q"
        ),
        "fallback": first_value(
            payload,
            "fallback"
        ),
        "error": first_value(
            payload,
            "error"
        ),
        "raw_payload_json": json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":")
        )
    })

    return {
        key: csv_value(value)
        for key, value in row.items()
    }

def append_csv_event(
    payload,
    default_event_type
):
    create_csv_if_needed()

    row = normalize_csv_row(
        payload,
        default_event_type
    )

    with csv_lock:
        with CSV_PATH.open(
            "a",
            newline="",
            encoding="utf-8-sig"
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=CSV_COLUMNS,
                extrasaction="ignore"
            )

            writer.writerow(
                row
            )


# TEST PAGE

@app.route("/", methods=["GET"])
def home():
    create_csv_if_needed()

    return jsonify({
        "status": "online",
        "message": (
            "AI server and CSV logger are running"
        ),
        "csv_file": str(
            CSV_PATH
        ),
        "download_url": (
            "http://127.0.0.1:5001/download-log"
        )
    })

# CSV LOGGING ENDPOINT FOR THE BUZZER

@app.route(
    "/log_batch",
    methods=["POST"]
)
def log_batch():
    payload = request.get_json(
        silent=True
    )

    if not isinstance(
        payload,
        dict
    ):
        return jsonify({
            "ok": False,
            "error": (
                "Expected one JSON object"
            )
        }), 400

    events = payload.get(
        "events",
        []
    )

    if not isinstance(
        events,
        list
    ):
        return jsonify({
            "ok": False,
            "error": (
                "events must be a list"
            )
        }), 400

    written = 0

    for event in events:
        if isinstance(
            event,
            dict
        ):
            append_csv_event(
                event,
                "BUZZER_EVENT"
            )

            written += 1

    print(
        "CSV rows received from buzzer:",
        written
    )

    return jsonify({
        "ok": True,
        "written": written
    })


@app.route(
    "/download-log",
    methods=["GET"]
)
def download_log():
    create_csv_if_needed()

    return send_file(
        CSV_PATH,
        as_attachment=True,
        download_name=(
            "interaction_log.csv"
        ),
        mimetype="text/csv"
    )



# AI prompt


@app.route(
    "/prompt",
    methods=["POST"]
)
def prompt():
    stats = request.get_json(
        silent=True
    )

    if not isinstance(
        stats,
        dict
    ):
        return jsonify({
            "error": (
                "No valid JSON object was received"
            )
        }), 400

    # Keep the exact input that caused this prompt.
    ai_input_json = json.dumps(
        stats,
        ensure_ascii=False,
        sort_keys=True
    )

    ai_request_row = dict(
        stats
    )

    ai_request_row.update({
        "event_type": "AI_REQUEST",
        "device_id": stats.get(
            "device_id",
            "BUZZER_ESP32"
        ),
        "ai_input_json": ai_input_json,
        "ai_behavior": stats.get(
            "behavior",
            "UNKNOWN"
        ),
        "ai_status": "requested",
        "ai_model": GEMINI_MODEL
    })

    append_csv_event(
        ai_request_row,
        "AI_REQUEST"
    )

    fallback_quote = (
        "Give your attention a quiet moment before you continue."
    )

    quote = fallback_quote
    fallback_used = True
    ai_status = "fallback"
    error_message = ""

    try:

        # READ DATA FROM THE BUZZER UNIT

        duration_seconds = float(
            stats.get(
                "duration",
                0
            )
        )

        button_presses = int(
            stats.get(
                "btns",
                0
            )
        )

        # The buzzer may send both wheel and pot_activity.
        # pot_activity has priority.
        pot_activity = int(
            stats.get(
                "pot_activity",
                stats.get(
                    "wheel",
                    0
                )
            )
        )

        max_static = float(
            stats.get(
                "max_static",
                0
            )
        )

        current_static = float(
            stats.get(
                "current_static",
                0
            )
        )

        total_static = float(
            stats.get(
                "total_static",
                0
            )
        )

        motion_seconds = float(
            stats.get(
                "motion_seconds",
                0
            )
        )

        engagement_detected = bool(
            int(
                stats.get(
                    "engagement_detected",
                    0
                )
            )
        )

        behavior = str(
            stats.get(
                "behavior",
                "UNKNOWN"
            )
        ).upper()

        pet_status = str(
            stats.get(
                "pet_status",
                "GHOST"
            )
        ).upper()

        reaction_time = float(
            stats.get(
                "reaction_time",
                0
            )
        )

        duration_minutes = round(
            duration_seconds / 60,
            1
        )

        rate_minutes = (
            duration_seconds / 60.0
        )

        if rate_minutes < 1.0:
            rate_minutes = 1.0

        button_presses_per_minute = round(
            button_presses / rate_minutes,
            2
        )

        pot_activity_per_minute = round(
            pot_activity / rate_minutes,
            2
        )

        motion_seconds_per_minute = round(
            motion_seconds / rate_minutes,
            2
        )

        # EXPLAIN THE CLASSIFIED BEHAVIOR TO GEMINI


        behavior_descriptions = {
            "ZOMBIE": (
                "The phone remained almost completely still for "
                "a prolonged period with very little interaction. "
                "This may represent absorbed or passive viewing."
            ),

            "RESTLESS": (
                "There was high potentiometer activity, several "
                "button presses and a lot of physical phone movement."
            ),

            "CHECKER": (
                "There were repeated button presses and frequent "
                "movement, but relatively little potentiometer activity."
            ),

            "HYPER": (
                "There was an extremely high amount of repetitive "
                "potentiometer activity."
            ),

            "NORMAL": (
                "No clearly problematic phone-use pattern was detected."
            ),

            "UNKNOWN": (
                "The exact phone-use pattern is unknown."
            )
        }

        behavior_description = (
            behavior_descriptions.get(
                behavior,
                behavior_descriptions[
                    "UNKNOWN"
                ]
            )
        )

        # PROMPT FOR GEMINI
        prompt = f"""
You are analysing a phone-use session for a digital wellbeing
project with a virtual pet.

Measured data:

- Session duration: {duration_minutes} minutes
- Number of button presses: {button_presses}
- Average button presses per minute: {button_presses_per_minute}
- Total potentiometer activity: {pot_activity}
- Average potentiometer activity per minute: {pot_activity_per_minute}
- Longest uninterrupted still period: {max_static} seconds
- Current uninterrupted still period: {current_static} seconds
- Total still time: {total_static} seconds
- Time with clearly detected movement: {motion_seconds} seconds
- Average movement time per minute: {motion_seconds_per_minute} seconds
- Engagement detected: {engagement_detected}
- Classified behavior: {behavior}
- Behavior explanation: {behavior_description}
- Pet status when the alarm started: {pet_status}
- Reaction time to the red button: {reaction_time} seconds

Write one short English reflective quote for the user.

Rules:
- Maximum 80 characters
- Friendly and non-judgmental
- Relevant to the measured pattern
- Do not mention numbers
- Do not make a diagnosis
- Do not use quotation marks
- Return only the quote
"""
-
        # CALL GEMINI

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type=(
                    "application/json"
                ),
                response_json_schema={
                    "type": "object",
                    "properties": {
                        "quote": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "quote"
                    ]
                }
            )
        )


        # PROCESS THE RESPONSE


        result = json.loads(
            response.text
        )

        quote = str(
            result.get(
                "quote",
                fallback_quote
            )
        ).strip()

        # Extra protection for the small LCD.
        if len(quote) > 100:
            quote = quote[:100]

        fallback_used = False
        ai_status = "success"

    except Exception as error:
        error_message = repr(
            error
        )

        print("--------------------------------")
        print("Error during AI analysis:")
        print(error_message)
        print("--------------------------------")

    ai_response_row = dict(
        stats
    )

    ai_response_row.update({
        "event_type": "AI_RESPONSE",
        "device_id": stats.get(
            "device_id",
            "BUZZER_ESP32"
        ),
        "ai_input_json": ai_input_json,
        "ai_behavior": stats.get(
            "behavior",
            "UNKNOWN"
        ),
        "ai_status": ai_status,
        "ai_model": GEMINI_MODEL,
        "gemini_quote": quote,
        "fallback": fallback_used,
        "error": error_message
    })

    append_csv_event(
        ai_response_row,
        "AI_RESPONSE"
    )

    print("--------------------------------")
    print("Data received from ESP32:")
    print(stats)
    print(
        "Behavior:",
        stats.get(
            "behavior",
            "UNKNOWN"
        )
    )
    print(
        "Gemini quote:",
        quote
    )
    print(
        "CSV file:",
        CSV_PATH
    )
    print("--------------------------------")

    return jsonify({
        "quote": quote,
        "ai_status": ai_status,
        "fallback": fallback_used,
        "error": error_message
    }), 200


# =============================================================
# START SERVER
# =============================================================

if __name__ == "__main__":
    create_csv_if_needed()

    print(
        "AI server and CSV logger are starting..."
    )

    print(
        "Local test: "
    )

    print(
        "Download CSV: "
    )

    print(
        "CSV file:",
        CSV_PATH
    )

    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False,
        threaded=True
    )

