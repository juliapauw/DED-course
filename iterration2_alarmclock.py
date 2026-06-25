import network
import espnow
import time
import gc
import ujson as json

from machine import Pin, PWM, SoftSPI

try:
    import usocket as socket
except ImportError:
    import socket

# WI-FI AND MAC SERVER


WIFI_SSID = ""
WIFI_PASSWORD = ""

SERVER_HOST = ""
SERVER_PORT = ''

AI_PATH = "/reflection"
CSV_LOG_PATH = "/log_batch"


CSV_STATUS_INTERVAL_MS = 10000

CSV_LOG_BATCH_SIZE = 3

CSV_LOG_MAX_BUFFER = 12
CSV_LOG_RETRY_MS = 10000
HTTP_TIMEOUT_SECONDS = 4

DEVICE_ID = "BUZZER_ESP32"

BROADCAST = b"\xff\xff\xff\xff\xff\xff"

# Compact phone packets fit comfortably inside this buffer.
ESPNOW_RX_BUFFER_SIZE = 512



# RED BUTTON

RED_BUTTON_GPIO = 22

# Not pressed = 1
# Pressed = 0
red_button = Pin(
    RED_BUTTON_GPIO,
    Pin.IN,
    Pin.PULL_UP
)

# BUZZERS

BUZZER1_GPIO = 25
BUZZER2_GPIO = 21

# Active-high buzzers:
# duty(0) = silent
# duty greater than 0 = sound

buzzer1_pin = Pin(
    BUZZER1_GPIO,
    Pin.OUT
)

buzzer2_pin = Pin(
    BUZZER2_GPIO,
    Pin.OUT
)

buzzer1_pin.value(0)
buzzer2_pin.value(0)

buzzer1 = PWM(
    buzzer1_pin
)

buzzer2 = PWM(
    buzzer2_pin
)

buzzer1.freq(1000)
buzzer2.freq(1000)

buzzer1.duty(0)
buzzer2.duty(0)

# LED MATRIX

LED_DIN_GPIO = 23
LED_CS_GPIO = 5
LED_CLK_GPIO = 18

cs = Pin(
    LED_CS_GPIO,
    Pin.OUT
)

cs.value(1)

spi = SoftSPI(
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(LED_CLK_GPIO),
    mosi=Pin(LED_DIN_GPIO),
    miso=Pin(19)
)


def max7219_write(register, data):
    cs.value(0)

    spi.write(
        bytearray([
            register,
            data
        ])
    )

    cs.value(1)


def clear_matrix():
    for row in range(1, 9):
        max7219_write(
            row,
            0x00
        )


def max7219_init():
    settings = [
        (0x0F, 0),  # Display test off
        (0x09, 0),  # No decode mode
        (0x0B, 7),  # Use all eight rows
        (0x0A, 0),  # Lowest brightness
        (0x0C, 1)   # Display on
    ]

    for register, value in settings:
        max7219_write(
            register,
            value
        )

    clear_matrix()


def display_matrix(pattern):
    for index in range(8):
        max7219_write(
            index + 1,
            pattern[index]
        )


# NORMAL / BALANCE
ROBOT_NORMAL = [
    0b11111111,
    0b11111111,
    0b11011011,
    0b11011011,
    0b11111111,
    0b11011011,
    0b11100111,
    0b11111111
]


# ZOMBIE
ROBOT_ZOMBIE = [
    0b11111111,
    0b11111111,
    0b10011001,
    0b11111111,
    0b11111111,
    0b11000011,
    0b11111111,
    0b11111111
]


# HYPER
ROBOT_HYPER = [
    0b11111111,
    0b11111111,
    0b10011001,
    0b10011001,
    0b11111111,
    0b11000011,
    0b11111111,
    0b11111111
]


# CHECKER
ROBOT_CHECKER = [
    0b11111111,
    0b10011001,
    0b10011001,
    0b11111111,
    0b11100111,
    0b11100111,
    0b11100111,
    0b11111111
]


# RESTLESS
ROBOT_RESTLESS = [
    0b11111111,
    0b10111101,
    0b11011011,
    0b10111101,
    0b11111111,
    0b11000011,
    0b11111111,
    0b11111111
]


# ghost
ROBOT_GHOST = [
   0b00111100,
    0b01111110,
    0b11111111,
    0b10011001,
    0b11111111,
    0b11111111,
    0b10101010,
    0b01010101
]

# LCD


LCD_RS_GPIO = 13
LCD_E_GPIO = 14
LCD_D4_GPIO = 27
LCD_D5_GPIO = 26
LCD_D6_GPIO = 32
LCD_D7_GPIO = 33


def make_lcd_safe(text):
    text = str(text)

    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "•": "-",
        "é": "e",
        "ë": "e",
        "è": "e",
        "ê": "e",
        "á": "a",
        "à": "a",
        "ä": "a",
        "â": "a",
        "í": "i",
        "ï": "i",
        "ó": "o",
        "ö": "o",
        "ú": "u",
        "ü": "u"
    }

    for old_character, new_character in replacements.items():
        text = text.replace(
            old_character,
            new_character
        )

    safe_text = ""

    for character in text:
        character_code = ord(
            character
        )

        if 32 <= character_code <= 126:
            safe_text += character
        else:
            safe_text += "?"

    return safe_text


def pad_lcd_text(
    text,
    width=16
):
    text = make_lcd_safe(
        text
    )

    text = text[:width]

    missing_spaces = (
        width - len(text)
    )

    if missing_spaces > 0:
        text += (
            " " * missing_spaces
        )

    return text


class LCD:
    def __init__(
        self,
        rs,
        enable,
        d4,
        d5,
        d6,
        d7
    ):
        self.rs = Pin(
            rs,
            Pin.OUT
        )

        self.enable = Pin(
            enable,
            Pin.OUT
        )

        self.data_pins = [
            Pin(d4, Pin.OUT),
            Pin(d5, Pin.OUT),
            Pin(d6, Pin.OUT),
            Pin(d7, Pin.OUT)
        ]

        self.rs.value(0)
        self.enable.value(0)

        time.sleep_ms(50)

        for _ in range(3):
            self.write4bits(
                0x03
            )

            time.sleep_ms(5)

        self.write4bits(
            0x02
        )

        for command in [
            0x28,
            0x0C,
            0x06,
            0x01
        ]:
            self.command(
                command
            )

    def pulse_enable(self):
        self.enable.value(0)
        time.sleep_us(2)

        self.enable.value(1)
        time.sleep_us(2)

        self.enable.value(0)
        time.sleep_us(150)

    def write4bits(
        self,
        value
    ):
        for index in range(4):
            self.data_pins[index].value(
                (value >> index) & 1
            )

        self.pulse_enable()

    def send(
        self,
        value,
        mode
    ):
        self.rs.value(
            mode
        )

        self.write4bits(
            (value >> 4) & 0x0F
        )

        self.write4bits(
            value & 0x0F
        )

    def command(
        self,
        value
    ):
        self.send(
            value,
            0
        )

        time.sleep_ms(2)

    def write_char(
        self,
        character
    ):
        safe_character = make_lcd_safe(
            character
        )

        if not safe_character:
            safe_character = "?"

        try:
            self.send(
                ord(
                    safe_character[0]
                ),
                1
            )

        except Exception:
            self.send(
                ord("?"),
                1
            )

        time.sleep_ms(1)

    def clear(self):
        self.command(
            0x01
        )

        time.sleep_ms(3)

    def move_to(
        self,
        column,
        row
    ):
        address = column

        if row == 1:
            address += 0x40

        self.command(
            0x80 | address
        )

    def putstr(
        self,
        text
    ):
        safe_text = make_lcd_safe(
            text
        )

        for character in safe_text:
            self.write_char(
                character
            )

    def print_lines(
        self,
        line1,
        line2=""
    ):
        safe_line1 = pad_lcd_text(
            line1,
            16
        )

        safe_line2 = pad_lcd_text(
            line2,
            16
        )

        self.clear()

        self.move_to(
            0,
            0
        )

        self.putstr(
            safe_line1
        )

        self.move_to(
            0,
            1
        )

        self.putstr(
            safe_line2
        )

    def scroll_text(
        self,
        text,
        title="Your reflection:",
        delay=0.30
    ):
        safe_text = make_lcd_safe(
            text
        )

        safe_title = pad_lcd_text(
            title,
            16
        )

        self.clear()

        self.move_to(
            0,
            0
        )

        self.putstr(
            safe_title
        )

        padded_text = (
            " " * 16
            + safe_text
            + " " * 16
        )

        for index in range(
            len(padded_text) - 15
        ):
            visible_text = padded_text[
                index:index + 16
            ]

            visible_text = pad_lcd_text(
                visible_text,
                16
            )

            self.move_to(
                0,
                1
            )

            self.putstr(
                visible_text
            )

            time.sleep(
                delay
            )

# WIFI


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

# SHOW ROBOT FACE

current_face_name = "BALANCE"
current_lcd_line1 = "(^_^) BALANCE"
current_lcd_line2 = "Calm phone use"


def set_pet_display(
    face_name,
    pattern,
    line1,
    line2
):
    global current_face_name
    global current_lcd_line1
    global current_lcd_line2

    current_face_name = str(
        face_name
    )

    current_lcd_line1 = str(
        line1
    )[:16]

    current_lcd_line2 = str(
        line2
    )[:16]

    display_matrix(
        pattern
    )

    lcd.print_lines(
        current_lcd_line1,
        current_lcd_line2
    )


def show_behavior_face(
    behavior,
    pet_status="HAPPY"
):
    behavior = str(
        behavior
    ).upper()

    pet_status = str(
        pet_status
    ).upper()

    # The alarm ghost always has priority.
    if pet_status == "GHOST":
        set_pet_display(
            "GHOST",
            ROBOT_GHOST,
            "(X_X) ALARM",
            "Press red button"
        )

        return

    if behavior == "HYPER":
        set_pet_display(
            "HYPER",
            ROBOT_HYPER,
            "(O_O) HYPER",
            "Too much input"
        )

    elif behavior == "CHECKER":
        set_pet_display(
            "CHECKER",
            ROBOT_CHECKER,
            "(o_O) CHECKER",
            "Seeking stimuli"
        )

    elif behavior == "ZOMBIE":
        set_pet_display(
            "ZOMBIE",
            ROBOT_ZOMBIE,
            "(-_-) ZOMBIE",
            "Absorbed scroll"
        )

    elif behavior == "RESTLESS":
        set_pet_display(
            "RESTLESS",
            ROBOT_RESTLESS,
            "(>_<) RESTLESS",
            "High stress"
        )

    else:
        set_pet_display(
            "BALANCE",
            ROBOT_NORMAL,
            "(^_^) BALANCE",
            "Calm phone use"
        )


# LIGHTWEIGHT HTTP THROUGH THE MAC SERVER


def ensure_wifi_for_logging():
    wlan = network.WLAN(
        network.STA_IF
    )

    wlan.active(True)

    if wlan.isconnected():
        return True

    try:
        wlan.connect(
            WIFI_SSID,
            WIFI_PASSWORD
        )

    except Exception as error:
        print(
            "Wi-Fi reconnect command failed:",
            error
        )

    timeout = 20

    while (
        not wlan.isconnected()
        and timeout > 0
    ):
        time.sleep(1)
        timeout -= 1

    return wlan.isconnected()


def socket_send_all(
    sock,
    data
):
    position = 0

    while position < len(data):
        sent = sock.send(
            data[position:]
        )

        if not sent:
            raise OSError(
                "Socket send failed"
            )

        position += sent


def http_post_json(
    path,
    payload
):
    sock = None

    gc.collect()

    try:
        if not ensure_wifi_for_logging():
            raise OSError(
                "No Wi-Fi connection"
            )

        body = json.dumps(
            payload
        ).encode()

        address = socket.getaddrinfo(
            SERVER_HOST,
            SERVER_PORT
        )[0][-1]

        sock = socket.socket()

        sock.settimeout(
            HTTP_TIMEOUT_SECONDS
        )

        sock.connect(
            address
        )

        header = (
            "POST {} HTTP/1.0\r\n"
            "Host: {}:{}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(
            path,
            SERVER_HOST,
            SERVER_PORT,
            len(body)
        ).encode()

        socket_send_all(
            sock,
            header
        )

        socket_send_all(
            sock,
            body
        )

        response = b""

        while len(response) < 8192:
            chunk = sock.recv(
                512
            )

            if not chunk:
                break

            response += chunk

        if b"\r\n\r\n" not in response:
            raise OSError(
                "Invalid HTTP response"
            )

        response_header, response_body = response.split(
            b"\r\n\r\n",
            1
        )

        status_line = response_header.split(
            b"\r\n",
            1
        )[0]

        success = (
            b" 200 " in status_line
        )

        result = {}

        if response_body:
            try:
                result = json.loads(
                    response_body.decode()
                )

            except Exception:
                result = {}

        return success, result

    except Exception as error:
        print(
            "HTTP error:",
            error
        )

        return False, {}

    finally:
        if sock is not None:
            try:
                sock.close()

            except Exception:
                pass

        gc.collect()

# AI THROUGH THE MAC SERVER

def get_ai_reflection(stats):
    print(
        ">>> Sending measurements to the Mac server"
    )

    lcd.print_lines(
        "AI analysis...",
        "Please wait"
    )

    fallback_quote = (
        "Pause and take a conscious break from your screen."
    )

    payload = {
        "duration": stats.get(
            "duration",
            0
        ),
        "btns": stats.get(
            "btns",
            0
        ),
        "pot_raw": stats.get(
            "pot_raw",
            ""
        ),
        "pot_activity": stats.get(
            "pot_activity",
            0
        ),
        "motion": stats.get(
            "motion",
            ""
        ),
        "max_static": stats.get(
            "max_static",
            0
        ),
        "current_static": stats.get(
            "current_static",
            0
        ),
        "total_static": stats.get(
            "total_static",
            0
        ),
        "motion_seconds": stats.get(
            "motion_seconds",
            0
        ),
        "engagement_detected": stats.get(
            "engagement_detected",
            0
        ),
        "behavior": stats.get(
            "behavior",
            "UNKNOWN"
        ),
        "pet_status": stats.get(
            "pet_status",
            "GHOST"
        ),
        "reaction_time": stats.get(
            "reaction_time",
            0
        ),
        "session_id": stats.get(
            "session_id",
            current_session_id
        ),
        "measurement_id": stats.get(
            "measurement_id",
            make_measurement_id(
                stats
            )
        )
    }

    print(
        "Data sent to AI server:"
    )

    print(
        payload
    )

    # Upload important queued events before the one-time AI request.
    flush_csv_log(
        force=True
    )

    success, result = http_post_json(
        AI_PATH,
        payload
    )

    if not success:
        print(
            ">>> AI server unavailable"
        )

        return fallback_quote

    quote = result.get(
        "quote",
        fallback_quote
    )

    print(
        "AI quote received:"
    )

    print(
        quote
    )

    return quote

# ALARM

REST = 0

alarm_active = False
alarm_step = 0

last_alarm_toggle_time = (
    time.ticks_ms()
)

ALARM_PATTERN = [

    # TOK — TOK-TOK — DING


    # TOK: buzzer 1
    (420, REST, 0.11),

    # Pause
    (REST, REST, 0.55),

    # TOK: buzzer 2
    (REST, 520, 0.09),

    # Short pause
    (REST, REST, 0.10),

    # TOK: buzzer 1
    (520, REST, 0.09),

    # Pause before ding
    (REST, REST, 0.40),

    # DING: buzzer 2
    (REST, 1100, 0.32),

    # Longer pause
    (REST, REST, 1.40),

    # VARIATION: TOK — TOK-TOK — DING-DING

    # TOK
    (420, REST, 0.11),

    # Pause
    (REST, REST, 0.55),

    # TOK
    (REST, 520, 0.09),

    # Short pause
    (REST, REST, 0.10),

    # TOK
    (520, REST, 0.09),

    # Pause before ding
    (REST, REST, 0.40),

    # First DING
    (REST, 1000, 0.22),

    # Short pause
    (REST, REST, 0.12),

    # Unexpected second DING
    (1300, REST, 0.28),

    # Pause before repeating everything
    (REST, REST, 1.70)
]


def stop_buzzers():
    buzzer1.duty(0)
    buzzer2.duty(0)


def start_two_buzzer_tone(
    frequency1,
    frequency2
):
    if frequency1 != REST:
        buzzer1.freq(
            frequency1
        )

        buzzer1.duty(
            300
        )

    else:
        buzzer1.duty(
            0
        )

    if frequency2 != REST:
        buzzer2.freq(
            frequency2
        )

        buzzer2.duty(
            220
        )

    else:
        buzzer2.duty(
            0
        )


def start_alarm():
    global alarm_active
    global alarm_step
    global last_alarm_toggle_time

    if alarm_active:
        return

    alarm_active = True
    alarm_step = 0

    last_alarm_toggle_time = (
        time.ticks_ms()
    )

    show_behavior_face(
        "ALARM",
        "GHOST"
    )

    (
        frequency1,
        frequency2,
        duration
    ) = ALARM_PATTERN[
        alarm_step
    ]

    start_two_buzzer_tone(
        frequency1,
        frequency2
    )

    print(
        "Alarm started"
    )


def stop_alarm():
    global alarm_active
    global alarm_step

    alarm_active = False
    alarm_step = 0

    stop_buzzers()

    print(
        "Alarm stopped"
    )


def update_alarm():
    global alarm_step
    global last_alarm_toggle_time

    if not alarm_active:
        return

    now_ms = time.ticks_ms()

    (
        frequency1,
        frequency2,
        duration
    ) = ALARM_PATTERN[
        alarm_step
    ]

    if (
        time.ticks_diff(
            now_ms,
            last_alarm_toggle_time
        )
        >= int(duration * 1000)
    ):
        alarm_step += 1

        if alarm_step >= len(
            ALARM_PATTERN
        ):
            alarm_step = 0

        (
            frequency1,
            frequency2,
            duration
        ) = ALARM_PATTERN[
            alarm_step
        ]

        start_two_buzzer_tone(
            frequency1,
            frequency2
        )

        last_alarm_toggle_time = (
            now_ms
        )


# CSV LOGGING THROUGH THE MAC SERVER

csv_log_buffer = []
csv_event_counter = 0
csv_session_counter = 0
current_session_id = ""
last_csv_attempt_ms = 0


def start_new_csv_session():
    global csv_session_counter
    global current_session_id

    csv_session_counter += 1

    current_session_id = (
        str(time.ticks_ms())
        + "-"
        + str(csv_session_counter)
    )

    print(
        "CSV session ID:",
        current_session_id
    )


def make_measurement_id(stats):
    existing_id = stats.get(
        "measurement_id",
        ""
    )

    if existing_id:
        return str(
            existing_id
        )

    return (
        str(
            stats.get(
                "session_id",
                current_session_id
            )
        )
        + "-"
        + str(
            stats.get(
                "duration",
                0
            )
        )
        + "s"
    )


def post_log_batch(events):
    success, result = http_post_json(
        CSV_LOG_PATH,
        {
            "events": events
        }
    )

    return success


def flush_csv_log(
    force=False
):
    global last_csv_attempt_ms

    if not csv_log_buffer:
        return True

    if (
        not force
        and len(csv_log_buffer) < CSV_LOG_BATCH_SIZE
    ):
        return True

    now_ms = time.ticks_ms()

    if (
        not force
        and time.ticks_diff(
            now_ms,
            last_csv_attempt_ms
        ) < CSV_LOG_RETRY_MS
    ):
        return False

    last_csv_attempt_ms = now_ms

    while csv_log_buffer:
        send_count = min(
            CSV_LOG_BATCH_SIZE,
            len(csv_log_buffer)
        )

        rows_to_send = csv_log_buffer[
            :send_count
        ]

        if not post_log_batch(
            rows_to_send
        ):
            while len(
                csv_log_buffer
            ) > CSV_LOG_MAX_BUFFER:
                csv_log_buffer.pop(
                    0
                )

            return False

        del csv_log_buffer[
            :send_count
        ]

        print(
            "CSV rows uploaded:",
            send_count
        )

        if not force:
            break

    return True

def build_csv_event(
    event_type,
    stats=None,
    extra=None
):
    global csv_event_counter

    if stats is None:
        stats = {}

    csv_event_counter += 1

    session_id = str(
        stats.get(
            "session_id",
            current_session_id
        )
    )

    event = {
        "ev": event_type,
        "eid": (
            session_id
            + "-"
            + str(csv_event_counter)
        ),
        "sid": session_id,
        "mid": make_measurement_id(
            stats
        ),
        "dev": DEVICE_ID,
        "up": time.ticks_ms(),
        "src": stats.get(
            "type",
            ""
        ),
        "d": stats.get(
            "duration",
            0
        ),
        "b": stats.get(
            "btns",
            0
        ),
        "pr": stats.get(
            "pot_raw",
            ""
        ),
        "pa": stats.get(
            "pot_activity",
            0
        ),
        "m": stats.get(
            "motion",
            ""
        ),
        "ms": stats.get(
            "motion_seconds",
            0
        ),
        "mx": stats.get(
            "max_static",
            0
        ),
        "cs": stats.get(
            "current_static",
            0
        ),
        "ts": stats.get(
            "total_static",
            0
        ),
        "e": stats.get(
            "engagement_detected",
            0
        ),
        "bh": stats.get(
            "behavior",
            "UNKNOWN"
        ),
        "ps": stats.get(
            "pet_status",
            "UNKNOWN"
        ),
        "ba": (
            1 if alarm_active else 0
        ),
        "face": current_face_name,
        "l1": current_lcd_line1,
        "l2": current_lcd_line2,
        "step": alarm_step,
        "rb": (
            1 if red_button.value() == 0 else 0
        )
    }

    if extra:
        event.update(
            extra
        )

    return event


def queue_csv_event(
    event_type,
    stats=None,
    extra=None,
    force=False
):
    csv_log_buffer.append(
        build_csv_event(
            event_type,
            stats,
            extra
        )
    )

    while len(
        csv_log_buffer
    ) > CSV_LOG_MAX_BUFFER:
        csv_log_buffer.pop(
            0
        )

    flush_csv_log(
        force=force
    )


def prepare_received_packet(packet):
    compact_type = str(
        packet.get(
            "t",
            ""
        )
    )

    packet_type = packet.get(
        "type",
        ""
    )

    if not packet_type:
        packet_type = {
            "S": "PHONE_STATUS",
            "A": "ALARM_AI",
            "O": "SESSION_OK",
            "R": "RESET_SCORE"
        }.get(
            compact_type,
            ""
        )

    prepared = {
        "type": packet_type,
        "duration": packet.get(
            "duration",
            packet.get(
                "d",
                0
            )
        ),
        "btns": packet.get(
            "btns",
            packet.get(
                "b",
                0
            )
        ),
        "pot_raw": packet.get(
            "pot_raw",
            packet.get(
                "pr",
                ""
            )
        ),
        "pot_activity": packet.get(
            "pot_activity",
            packet.get(
                "pa",
                0
            )
        ),
        "motion": packet.get(
            "motion",
            packet.get(
                "m",
                ""
            )
        ),
        "max_static": packet.get(
            "max_static",
            packet.get(
                "mx",
                0
            )
        ),
        "current_static": packet.get(
            "current_static",
            packet.get(
                "cs",
                0
            )
        ),
        "total_static": packet.get(
            "total_static",
            packet.get(
                "ts",
                0
            )
        ),
        "motion_seconds": packet.get(
            "motion_seconds",
            packet.get(
                "ms",
                0
            )
        ),
        "engagement_detected": packet.get(
            "engagement_detected",
            packet.get(
                "e",
                0
            )
        ),
        "behavior": packet.get(
            "behavior",
            packet.get(
                "bh",
                "NORMAL"
            )
        ),
        "pet_status": packet.get(
            "pet_status",
            packet.get(
                "ps",
                "HAPPY"
            )
        )
    }

    prepared["session_id"] = packet.get(
        "session_id",
        packet.get(
            "s",
            current_session_id
        )
    )

    prepared["measurement_id"] = packet.get(
        "measurement_id",
        make_measurement_id(
            prepared
        )
    )

    return prepared

# RESET PHONE CASE SESSION

def send_reset(esp_now):
    packet = {
        "t": "R"
    }

    message = json.dumps(
        packet
    ).encode()

    success_count = 0

    for _ in range(10):
        try:
            esp_now.send(
                BROADCAST,
                message
            )

            success_count += 1

        except Exception as error:
            print(
                "Could not send reset:",
                error
            )

        time.sleep(0.05)

    print(
        "RESET sent to phone case:",
        success_count,
        "of 10"
    )

    return success_count

def initialise_espnow():
    """Start ESP-NOW with a larger receive buffer."""
    esp_now = espnow.ESPNow()

    try:
        esp_now.active(False)
    except Exception:
        pass

    esp_now.active(True)

    try:
        esp_now.config(
            rxbuf=ESPNOW_RX_BUFFER_SIZE
        )

        esp_now.active(False)
        esp_now.active(True)

    except Exception as error:
        print(
            "Could not configure ESP-NOW receive buffer:",
            error
        )

    try:
        esp_now.add_peer(
            BROADCAST
        )

    except OSError as error:
        # This message is harmless: it only means the broadcast
        # peer was already registered.
        if (
            len(error.args) < 2
            or error.args[1] != "ESP_ERR_ESPNOW_EXIST"
        ):
            raise

    return esp_now


def safe_espnow_recv(
    esp_now,
    timeout_ms
):
    """Receive one message and recover from a buffer error."""
    try:
        host, message = esp_now.recv(
            timeout_ms
        )

        return esp_now, host, message

    except ValueError as error:
        if "buffer error" not in str(error):
            raise

        print(
            "ESP-NOW receive buffer error detected."
        )
        print(
            "Restarting ESP-NOW receiver..."
        )

        # Some MicroPython versions remain stuck after this
        # error until ESP-NOW is deactivated and reactivated.
        esp_now = initialise_espnow()

        return esp_now, None, None


def drain_espnow_queue(esp_now):
    while True:
        esp_now, host, message = safe_espnow_recv(
            esp_now,
            0
        )

        if not message:
            return esp_now

# MAIN PROGRAM

try:
    stop_buzzers()

    lcd = LCD(
        LCD_RS_GPIO,
        LCD_E_GPIO,
        LCD_D4_GPIO,
        LCD_D5_GPIO,
        LCD_D6_GPIO,
        LCD_D7_GPIO
    )

    max7219_init()

    lcd.print_lines(
        "Starting...",
        ""
    )

    display_matrix(
        ROBOT_NORMAL
    )

    wlan = connect_wifi()

    if not wlan.isconnected():
        raise Exception(
            "Buzzer unit has no Wi-Fi connection"
        )

    esp_now = initialise_espnow()

    try:
        print(
            "ESP-NOW maximum packet size:",
            espnow.MAX_DATA_LEN
        )
    except Exception:
        pass

    print(
        "Buzzer unit is ready"
    )

    start_new_csv_session()

    last_stats = {}

    current_pet_status = "HAPPY"
    current_behavior = "NORMAL"

    last_phone_csv_log_ms = time.ticks_add(
        time.ticks_ms(),
        -CSV_STATUS_INTERVAL_MS
    )

    last_logged_pet_status = ""
    last_logged_behavior = ""

    last_session_ok_ms = time.ticks_add(
        time.ticks_ms(),
        -5000
    )

    alarm_start_time = 0

    startup_ignore_until = (
        time.ticks_add(
            time.ticks_ms(),
            5000
        )
    )

    alarm_cooldown_until = (
        time.ticks_ms()
    )

    show_behavior_face(
        current_behavior,
        current_pet_status
    )

    queue_csv_event(
        "BUZZER_STARTED",
        force=False
    )

    while True:

        # ALWAYS SILENT WHEN NO ALARM IS ACTIVE


        if not alarm_active:
            buzzer1.duty(0)
            buzzer2.duty(0)

        # RED BUTTON

        if red_button.value() == 0:
            print(
                "Red button pressed"
            )

            stop_buzzers()

            if alarm_active:
                reaction_time = (
                    time.ticks_diff(
                        time.ticks_ms(),
                        alarm_start_time
                    )
                    / 1000.0
                )

                last_stats[
                    "reaction_time"
                ] = round(
                    reaction_time,
                    1
                )

                queue_csv_event(
                    "RED_BUTTON_PRESSED",
                    last_stats,
                    {
                        "rt": last_stats[
                            "reaction_time"
                        ]
                    },
                    force=True
                )

                stop_alarm()

                queue_csv_event(
                    "ALARM_STOPPED",
                    last_stats,
                    {
                        "rt": last_stats[
                            "reaction_time"
                        ]
                    },
                    force=True
                )

                lcd.print_lines(
                    "Restoring robot",
                    "AI is thinking..."
                )

                quote = get_ai_reflection(
                    last_stats
                )

                queue_csv_event(
                    "AI_QUOTE_DISPLAYED",
                    last_stats,
                    {
                        "rt": last_stats.get(
                            "reaction_time",
                            0
                        ),
                        "q": quote
                    },
                    force=False
                )

                display_matrix(
                    ROBOT_NORMAL
                )

                for _ in range(2):
                    lcd.scroll_text(
                        quote,
                        title="Your reflection:",
                        delay=0.25
                    )

                lcd.print_lines(
                    "New start",
                    "(^_^) BALANCE"
                )

                time.sleep(2)

                reset_success_count = send_reset(
                    esp_now
                )

                queue_csv_event(
                    "RESET_SENT",
                    last_stats,
                    {
                        "reset_count": (
                            reset_success_count
                        ),
                        "q": quote
                    },
                    force=True
                )

                start_new_csv_session()

                esp_now = drain_espnow_queue(
                    esp_now
                )

                alarm_cooldown_until = (
                    time.ticks_add(
                        time.ticks_ms(),
                        3000
                    )
                )

                current_pet_status = (
                    "HAPPY"
                )

                current_behavior = (
                    "NORMAL"
                )

                show_behavior_face(
                    current_behavior,
                    current_pet_status
                )

            else:
                print(
                    "No active alarm"
                )

                lcd.print_lines(
                    "No alarm",
                    "Robot balanced"
                )

                time.sleep(1)

                show_behavior_face(
                    current_behavior,
                    current_pet_status
                )

            while red_button.value() == 0:
                time.sleep_ms(20)

            time.sleep_ms(100)

        # RECEIVE ESP-NOW MESSAGES

        esp_now, host, message = safe_espnow_recv(
            esp_now,
            20
        )

        if message:
            print(
                "ESP-NOW received:"
            )

            print(
                message
            )

            try:
                packet = json.loads(
                    message.decode()
                )

                packet = prepare_received_packet(
                    packet
                )

                packet_type = packet.get(
                    "type",
                    ""
                )

                # LIVE BEHAVIOR

                if packet_type == "PHONE_STATUS":
                    received_pet_status = str(
                        packet.get(
                            "pet_status",
                            "HAPPY"
                        )
                    ).upper()

                    received_behavior = str(
                        packet.get(
                            "behavior",
                            "NORMAL"
                        )
                    ).upper()

                    print(
                        "PHONE_STATUS:",
                        received_pet_status,
                        "| behavior:",
                        received_behavior
                    )

                    if not alarm_active:
                        if (
                            received_pet_status
                            != current_pet_status
                            or received_behavior
                            != current_behavior
                        ):
                            current_pet_status = (
                                received_pet_status
                            )

                            current_behavior = (
                                received_behavior
                            )

                            show_behavior_face(
                                current_behavior,
                                current_pet_status
                            )

                    now_status_ms = time.ticks_ms()

                    state_changed = (
                        received_pet_status
                        != last_logged_pet_status
                        or received_behavior
                        != last_logged_behavior
                    )

                    log_interval_finished = (
                        time.ticks_diff(
                            now_status_ms,
                            last_phone_csv_log_ms
                        )
                        >= CSV_STATUS_INTERVAL_MS
                    )

                    if (
                        state_changed
                        or log_interval_finished
                    ):
                        queue_csv_event(
                            "PHONE_STATUS",
                            packet
                        )

                        last_phone_csv_log_ms = (
                            now_status_ms
                        )

                        last_logged_pet_status = (
                            received_pet_status
                        )

                        last_logged_behavior = (
                            received_behavior
                        )

                # ALARM AND AI

                elif packet_type == "ALARM_AI":
                    print(
                        "ALARM_AI received:"
                    )

                    print(
                        packet
                    )

                    startup_finished = (
                        time.ticks_diff(
                            time.ticks_ms(),
                            startup_ignore_until
                        )
                        >= 0
                    )

                    cooldown_finished = (
                        time.ticks_diff(
                            time.ticks_ms(),
                            alarm_cooldown_until
                        )
                        >= 0
                    )

                    if not startup_finished:
                        print(
                            "Alarm ignored during startup"
                        )

                    elif (
                        not alarm_active
                        and cooldown_finished
                    ):
                        last_stats = (
                            packet
                        )

                        current_pet_status = (
                            "GHOST"
                        )

                        current_behavior = str(
                            packet.get(
                                "behavior",
                                "UNKNOWN"
                            )
                        ).upper()

                        alarm_start_time = (
                            time.ticks_ms()
                        )

                        start_alarm()

                        queue_csv_event(
                            "ALARM_STARTED",
                            last_stats,
                            force=True
                        )


                # SESSION WITHOUT ALARM
  

                elif packet_type == "SESSION_OK":
                    now_ok_ms = time.ticks_ms()

                    if (
                        not alarm_active
                        and time.ticks_diff(
                            now_ok_ms,
                            last_session_ok_ms
                        ) > 1000
                    ):
                        last_session_ok_ms = (
                            now_ok_ms
                        )

                        stop_buzzers()

                        current_pet_status = (
                            "HAPPY"
                        )

                        current_behavior = (
                            "NORMAL"
                        )

                        show_behavior_face(
                            current_behavior,
                            current_pet_status
                        )

                        print(
                            "Session completed without alarm"
                        )

                        queue_csv_event(
                            "SESSION_OK",
                            packet,
                            force=True
                        )

                        start_new_csv_session()

                else:
                    print(
                        "Unknown packet type:",
                        packet_type
                    )

            except Exception as error:
                print(
                    "Message could not be processed:",
                    error
                )

        update_alarm()

        flush_csv_log(
            force=False
        )

        gc.collect()


except KeyboardInterrupt:
    print(
        "Program stopped"
    )

except Exception as error:
    print(
        "Unexpected error:",
        error
    )

finally:
    try:
        flush_csv_log(
            force=True
        )
    except Exception:
        pass

    stop_buzzers()
    clear_matrix()

