import network
import espnow
import time
import ujson as json

from machine import Pin, ADC, I2C



# WI-FI


WIFI_SSID = ""
WIFI_PASSWORD = ""



# PIN CONFIGURATION


BUTTON1_GPIO = 36
BUTTON2_GPIO = 37

POT_GPIO = 39

I2C_SCL_GPIO = 22
I2C_SDA_GPIO = 21



# 20-MINUTE MEASUREMENT

TICK_TIME = 0.2

SESSION_LIMIT_MINUTES = 20
SESSION_LIMIT_MS = SESSION_LIMIT_MINUTES * 60 * 1000

STATUS_SEND_INTERVAL_MS = 2000


DEBUG_PRINT_INTERVAL_MS = 2000



# SENSOR THRESHOLDS


# Ignore very small potentiometer changes as electrical noise.
POT_NOISE_THRESHOLD = 8

# Limit a single unusually large potentiometer step.
POT_MAX_STEP = 500

# A measurement at or above this value counts as movement.
MOTION_THRESHOLD = 2500



# REAL 20-MINUTE BEHAVIOR THRESHOLDS


# Potentiometer activity per minute.
POT_ACTIVITY_HIGH = 300
POT_ACTIVITY_EXTREME = 800
POT_ACTIVITY_LOW = 100

# Button presses per minute.
BUTTON_PRESSES_LOW = 2
BUTTON_PRESSES_HIGH = 3

# Active ZOMBIE
ZOMBIE_STATIC_SECONDS = 60

# Passive ZOMBIE
PASSIVE_ZOMBIE_SECONDS = 120

# RESTLESS and CHECKER require recent physical activity.
SHORT_STATIC_SECONDS = 30

# Clearly detected movement per minute.
RESTLESS_MOTION_SECONDS = 5



# INPUTS


button1 = Pin(
    BUTTON1_GPIO,
    Pin.IN
)

button2 = Pin(
    BUTTON2_GPIO,
    Pin.IN
)

pot = ADC(
    Pin(POT_GPIO)
)

pot.atten(
    ADC.ATTN_11DB
)

pot.width(
    ADC.WIDTH_12BIT
)

i2c = I2C(
    0,
    scl=Pin(I2C_SCL_GPIO),
    sda=Pin(I2C_SDA_GPIO),
    freq=400000
)



# ACCELEROMETER


MPU_ADDR = None


def find_accelerometer():
    devices = i2c.scan()

    print(
        "I2C devices:",
        [hex(device) for device in devices]
    )

    if 0x68 in devices:
        return 0x68

    if 0x69 in devices:
        return 0x69

    return None


def init_accelerometer():
    global MPU_ADDR

    MPU_ADDR = find_accelerometer()

    if MPU_ADDR is None:
        print(
            "No accelerometer found"
        )

        return False

    try:
        # Wake the MPU6050 from sleep mode.
        i2c.writeto_mem(
            MPU_ADDR,
            0x6B,
            b"\x00"
        )

        time.sleep(0.1)

        # Set the accelerometer range to +/- 2g.
        i2c.writeto_mem(
            MPU_ADDR,
            0x1C,
            b"\x00"
        )

        print(
            "Accelerometer started at",
            hex(MPU_ADDR)
        )

        return True

    except Exception as error:
        print(
            "Could not start accelerometer:",
            error
        )

        MPU_ADDR = None

        return False


def read_word(register):
    data = i2c.readfrom_mem(
        MPU_ADDR,
        register,
        2
    )

    value = (
        data[0] << 8
    ) | data[1]

    if value >= 32768:
        value -= 65536

    return value


def read_accelerometer():
    if MPU_ADDR is None:
        return 0, 0, 0

    try:
        ax = read_word(0x3B)
        ay = read_word(0x3D)
        az = read_word(0x3F)

        return ax, ay, az

    except Exception as error:
        print(
            "Could not read accelerometer:",
            error
        )

        return 0, 0, 0



# WI-FI



def connect_wifi():
    wlan = network.WLAN(
        network.STA_IF
    )

    wlan.active(True)

    if wlan.isconnected():
        print(
            "Wi-Fi was already connected:",
            wlan.ifconfig()
        )

        return wlan

    print(
        "Connecting to Wi-Fi:",
        WIFI_SSID
    )

    try:
        wlan.connect(
            WIFI_SSID,
            WIFI_PASSWORD
        )

    except Exception as error:
        print(
            "Wi-Fi connect command failed:",
            error
        )

    timeout = 60

    while (
        not wlan.isconnected()
        and timeout > 0
    ):
        print(
            "Wi-Fi status:",
            wlan.status()
        )

        time.sleep(1)
        timeout -= 1

    if wlan.isconnected():
        print(
            "Wi-Fi connected:",
            wlan.ifconfig()
        )

        try:
            print(
                "Wi-Fi channel:",
                wlan.config("channel")
            )

        except Exception:
            pass

    else:
        print(
            "Wi-Fi connection failed:",
            wlan.status()
        )

    return wlan


# SESSION VARIABLES


session_start_ms = 0

total_button_presses = 0
total_pot_activity = 0

static_streak_ticks = 0
max_static_time = 0.0
total_static_ticks = 0

motion_active_ticks = 0
total_motion_amount = 0

last_button1_state = 0
last_button2_state = 0

last_pot_raw = None

last_ax = 0
last_ay = 0
last_az = 0

first_motion_reading = True

last_status_send_ms = 0
last_debug_print_ms = 0

engagement_detected = False
intervention_active = False



# SENSOR FUNCTIONS



def read_buttons():
    # a physical pin value of 0 means pressed.
    button1_pressed = 1 if button1.value() == 0 else 0
    button2_pressed = 1 if button2.value() == 0 else 0

    return button1_pressed, button2_pressed


def read_pot_activity():
    global last_pot_raw

    pot_raw = pot.read()

    if last_pot_raw is None:
        raw_delta = 0
    else:
        raw_delta = abs(
            pot_raw - last_pot_raw
        )

    last_pot_raw = pot_raw

    if raw_delta <= POT_NOISE_THRESHOLD:
        useful_delta = 0
    else:
        useful_delta = min(
            raw_delta,
            POT_MAX_STEP
        )

    return pot_raw, useful_delta


def read_motion():
    global last_ax
    global last_ay
    global last_az
    global first_motion_reading

    ax, ay, az = read_accelerometer()

    # Store the first reading without counting it as movement.
    if first_motion_reading:
        last_ax = ax
        last_ay = ay
        last_az = az

        first_motion_reading = False

        return ax, ay, az, 0

    motion = (
        abs(ax - last_ax)
        + abs(ay - last_ay)
        + abs(az - last_az)
    )

    last_ax = ax
    last_ay = ay
    last_az = az

    return ax, ay, az, motion



# RESET SESSION

def reset_session():
    global session_start_ms

    global total_button_presses
    global total_pot_activity

    global static_streak_ticks
    global max_static_time
    global total_static_ticks

    global motion_active_ticks
    global total_motion_amount

    global last_button1_state
    global last_button2_state

    global last_pot_raw

    global last_ax
    global last_ay
    global last_az
    global first_motion_reading

    global last_status_send_ms
    global last_debug_print_ms

    global engagement_detected
    global intervention_active

    session_start_ms = time.ticks_ms()

    total_button_presses = 0
    total_pot_activity = 0

    static_streak_ticks = 0
    max_static_time = 0.0
    total_static_ticks = 0

    motion_active_ticks = 0
    total_motion_amount = 0

    last_button1_state = 0
    last_button2_state = 0

    last_pot_raw = None

    last_ax = 0
    last_ay = 0
    last_az = 0

    first_motion_reading = True

    last_status_send_ms = time.ticks_ms()
    last_debug_print_ms = time.ticks_ms()

    engagement_detected = False
    intervention_active = False


# ESP-NOW SENDING



def send_json_packet(
    esp_now,
    destination,
    packet
):
    try:
        message = json.dumps(
            packet
        ).encode()

        try:
            maximum_length = espnow.MAX_DATA_LEN
        except Exception:
            maximum_length = 250

        if len(message) > maximum_length:
            print(
                "ESP-NOW packet is too large:",
                len(message),
                "bytes; maximum:",
                maximum_length
            )

            return False

        esp_now.send(
            destination,
            message
        )

        return True

    except Exception as error:
        print(
            "ESP-NOW send failed:",
            error
        )

        return False


def send_repeated_packet(
    esp_now,
    destination,
    packet,
    repetitions
):
    success_count = 0

    for _ in range(repetitions):
        if send_json_packet(
            esp_now,
            destination,
            packet
        ):
            success_count += 1

        time.sleep(0.05)

    print(
        "Packet sent:",
        success_count,
        "of",
        repetitions
    )



# MESSAGES FROM THE BUZZER UNIT

def check_incoming_messages(esp_now):
    while True:
        host, message = esp_now.recv(0)

        if not message:
            break

        try:
            packet = json.loads(
                message.decode()
            )

            packet_type = packet.get(
                "type",
                ""
            )

            if not packet_type:
                packet_type = {
                    "R": "RESET_SCORE"
                }.get(
                    packet.get(
                        "t",
                        ""
                    ),
                    ""
                )

            if packet_type == "RESET_SCORE":
                print(
                    "RESET_SCORE received from buzzer unit"
                )

                reset_session()

        except Exception as error:
            print(
                "Incoming message could not be processed:",
                error
            )

# UPDATE SESSION MEASUREMENTS

def update_session_measurements(
    button1_pressed,
    button2_pressed,
    pot_delta,
    motion
):
    global total_button_presses
    global total_pot_activity

    global static_streak_ticks
    global max_static_time
    global total_static_ticks

    global motion_active_ticks
    global total_motion_amount

    global last_button1_state
    global last_button2_state

    global engagement_detected


    if (
        button1_pressed == 1
        or button2_pressed == 1
        or pot_delta > 0
        or motion >= MOTION_THRESHOLD
    ):
        if not engagement_detected:
            print(
                "Engagement detected"
            )

        engagement_detected = True


    if (
        button1_pressed == 1
        and last_button1_state == 0
    ):
        total_button_presses += 1

        print(
            "Button 1 counted. Total:",
            total_button_presses
        )

    if (
        button2_pressed == 1
        and last_button2_state == 0
    ):
        total_button_presses += 1

        print(
            "Button 2 counted. Total:",
            total_button_presses
        )

    last_button1_state = button1_pressed
    last_button2_state = button2_pressed

    total_pot_activity += pot_delta
    total_motion_amount += motion

    if motion >= MOTION_THRESHOLD:
        motion_active_ticks += 1
        static_streak_ticks = 0

    else:
        total_static_ticks += 1
        static_streak_ticks += 1

        current_static_seconds = (
            static_streak_ticks * TICK_TIME
        )

        if current_static_seconds > max_static_time:
            max_static_time = current_static_seconds

# BEHAVIOR CLASSIFICATION

def classify_behavior(
    pot_activity,
    button_presses,
    current_static_seconds,
    total_static_seconds,
    motion_seconds,
    engagement_was_detected,
    session_duration_ms
):

    elapsed_minutes = (
        session_duration_ms / 60000.0
    )

    if elapsed_minutes < 1.0:
        elapsed_minutes = 1.0

    button_presses_per_minute = (
        button_presses / elapsed_minutes
    )

    pot_activity_per_minute = (
        pot_activity / elapsed_minutes
    )

    motion_seconds_per_minute = (
        motion_seconds / elapsed_minutes
    )


    active_zombie = (
        engagement_was_detected
        and current_static_seconds >= ZOMBIE_STATIC_SECONDS
        and button_presses_per_minute <= BUTTON_PRESSES_LOW
    )


    passive_zombie = (
        current_static_seconds >= PASSIVE_ZOMBIE_SECONDS
        and button_presses_per_minute <= BUTTON_PRESSES_LOW
        and pot_activity_per_minute <= POT_ACTIVITY_LOW
    )

    is_zombie = (
        active_zombie
        or passive_zombie
    )

    is_restless = (
        pot_activity_per_minute >= POT_ACTIVITY_HIGH
        and current_static_seconds < SHORT_STATIC_SECONDS
        and button_presses_per_minute >= BUTTON_PRESSES_HIGH
        and motion_seconds_per_minute >= RESTLESS_MOTION_SECONDS
    )


    is_checker = (
        pot_activity_per_minute <= POT_ACTIVITY_LOW
        and current_static_seconds < SHORT_STATIC_SECONDS
        and button_presses_per_minute >= BUTTON_PRESSES_HIGH
        and motion_seconds_per_minute >= RESTLESS_MOTION_SECONDS
    )


    is_hyper = (
        pot_activity_per_minute >= POT_ACTIVITY_EXTREME
    )

    # Keep the original behavior priority unchanged.
    if is_zombie:
        return "ZOMBIE"

    if is_restless:
        return "RESTLESS"

    if is_checker:
        return "CHECKER"

    if is_hyper:
        return "HYPER"

    return "NORMAL"

def behavior_is_problematic(behavior):
    return behavior in (
        "ZOMBIE",
        "RESTLESS",
        "CHECKER",
        "HYPER"
    )

# AVATAR STATUS

def determine_avatar_status(
    session_duration_ms,
    behavior
):
    problematic = behavior_is_problematic(
        behavior
    )

    session_progress = (
        session_duration_ms
        / SESSION_LIMIT_MS
    )

    if (
        session_progress >= 1.0
        and problematic
    ):
        return "GHOST"

    if problematic:
        return "SICK"

    if session_progress < 0.30:
        return "HAPPY"

    if session_progress < 0.70:
        return "NEUTRAL"

    return "SICK"

# SERIAL DEBUG OUTPUT

def print_debug_if_needed(
    session_duration_ms,
    pot_raw,
    motion,
    motion_seconds,
    current_static_seconds,
    total_static_seconds,
    behavior,
    avatar_status
):
    global last_debug_print_ms

    now_ms = time.ticks_ms()

    if (
        time.ticks_diff(
            now_ms,
            last_debug_print_ms
        )
        < DEBUG_PRINT_INTERVAL_MS
    ):
        return

    print(
        "Time:",
        int(session_duration_ms / 1000),
        "sec",
        "| Buttons:",
        total_button_presses,
        "| Pot raw:",
        pot_raw,
        "| Pot activity:",
        total_pot_activity,
        "| Motion:",
        motion,
        "| Motion sec:",
        motion_seconds,
        "| Still now:",
        current_static_seconds,
        "| Total still:",
        total_static_seconds,
        "| Engagement:",
        engagement_detected,
        "| Behavior:",
        behavior,
        "| avatar:",
        avatar_status
    )

    last_debug_print_ms = now_ms

# SEND LIVE STATUS TO BUZZER UNIT

def send_status_if_needed(
    esp_now,
    destination,
    session_duration_ms,
    pot_raw,
    motion,
    behavior,
    avatar_status
):
    global last_status_send_ms

    now_ms = time.ticks_ms()

    if (
        time.ticks_diff(
            now_ms,
            last_status_send_ms
        )
        < STATUS_SEND_INTERVAL_MS
    ):
        return

    motion_seconds = round(
        motion_active_ticks * TICK_TIME,
        1
    )

    current_static_seconds = round(
        static_streak_ticks * TICK_TIME,
        1
    )

    total_static_seconds = round(
        total_static_ticks * TICK_TIME,
        1
    )

    status_packet = {
        "t": "S",
        "d": int(
            session_duration_ms / 1000
        ),
        "b": total_button_presses,
        "pr": pot_raw,
        "pa": total_pot_activity,
        "m": motion,
        "mx": round(
            max_static_time,
            1
        ),
        "cs": current_static_seconds,
        "ts": total_static_seconds,
        "ms": motion_seconds,
        "e": (
            1 if engagement_detected else 0
        ),
        "bh": behavior,
        "ps": avatar_status
    }

    if send_json_packet(
        esp_now,
        destination,
        status_packet
    ):
        print(
            "PHONE_STATUS sent:",
            avatar_status,
            "|",
            behavior
        )

    last_status_send_ms = now_ms


# EVALUATE SESSION AFTER TWENTY MINUTES

def evaluate_finished_session(
    esp_now,
    destination,
    session_duration_ms,
    pot_raw,
    motion,
    behavior,
    avatar_status
):
    global intervention_active

    motion_seconds = round(
        motion_active_ticks * TICK_TIME,
        1
    )

    current_static_seconds = round(
        static_streak_ticks * TICK_TIME,
        1
    )

    total_static_seconds = round(
        total_static_ticks * TICK_TIME,
        1
    )

    compact_data = {
        "d": int(
            session_duration_ms / 1000
        ),
        "b": total_button_presses,
        "pr": pot_raw,
        "pa": total_pot_activity,
        "m": motion,
        "mx": round(
            max_static_time,
            1
        ),
        "cs": current_static_seconds,
        "ts": total_static_seconds,
        "ms": motion_seconds,
        "e": (
            1 if engagement_detected else 0
        ),
        "bh": behavior,
        "ps": avatar_status
    }

    if behavior_is_problematic(
        behavior
    ):
        alarm_packet = {
            "t": "A"
        }

        alarm_packet.update(
            compact_data
        )

        send_repeated_packet(
            esp_now,
            destination,
            alarm_packet,
            reavataritions=10
        )

        intervention_active = True

    else:
        ok_packet = {
            "t": "O"
        }

        ok_packet.update(
            compact_data
        )

        send_repeated_packet(
            esp_now,
            destination,
            ok_packet,
            reavataritions=3
        )

        reset_session()

# MAIN PROGRAM

print(
    "Phone-case 20-MINUTE VERSION is starting"
)

init_accelerometer()

wlan = connect_wifi()

if not wlan.isconnected():
    raise Exception(
        "Phone case has no Wi-Fi connection"
    )

esp_now = espnow.ESPNow()
esp_now.active(True)

BROADCAST = b"\xff\xff\xff\xff\xff\xff"

try:
    esp_now.add_peer(
        BROADCAST
    )

except Exception as error:
    print(
        "Broadcast peer may already exist:",
        error
    )

print(
    "Phone-case ESP is ready"
)

reset_session()


while True:
    loop_start_ms = time.ticks_ms()

    check_incoming_messages(
        esp_now
    )

    button1_pressed, button2_pressed = read_buttons()

    pot_raw, pot_delta = read_pot_activity()

    ax, ay, az, motion = read_motion()

    if not intervention_active:
        update_session_measurements(
            button1_pressed,
            button2_pressed,
            pot_delta,
            motion
        )

    session_duration_ms = time.ticks_diff(
        time.ticks_ms(),
        session_start_ms
    )

    motion_seconds = round(
        motion_active_ticks * TICK_TIME,
        1
    )

    current_static_seconds = round(
        static_streak_ticks * TICK_TIME,
        1
    )

    total_static_seconds = round(
        total_static_ticks * TICK_TIME,
        1
    )

    behavior = classify_behavior(
        total_pot_activity,
        total_button_presses,
        current_static_seconds,
        total_static_seconds,
        motion_seconds,
        engagement_detected,
        session_duration_ms
    )

    avatar_status = determine_avatar_status(
        session_duration_ms,
        behavior
    )

    print_debug_if_needed(
        session_duration_ms,
        pot_raw,
        motion,
        motion_seconds,
        current_static_seconds,
        total_static_seconds,
        behavior,
        avatar_status
    )

    send_status_if_needed(
        esp_now,
        BROADCAST,
        session_duration_ms,
        pot_raw,
        motion,
        behavior,
        avatar_status
    )

    if (
        session_duration_ms >= SESSION_LIMIT_MS
        and not intervention_active
    ):
        evaluate_finished_session(
            esp_now,
            BROADCAST,
            session_duration_ms,
            pot_raw,
            motion,
            behavior,
            avatar_status
        )

    loop_duration_ms = time.ticks_diff(
        time.ticks_ms(),
        loop_start_ms
    )

    remaining_ms = int(
        TICK_TIME * 1000
    ) - loop_duration_ms

    if remaining_ms > 0:
        time.sleep_ms(
            remaining_ms
        )

