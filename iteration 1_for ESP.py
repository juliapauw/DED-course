import time
import ujson as json

from machine import Pin, ADC


# PIN SETTINGS


BUTTON_1_GPIO = 36
BUTTON_2_GPIO = 37
BUTTON_3_GPIO = 38

POT_GPIO = 4

# not pressed = 1
# pressed = 0
BUTTON_ACTIVE_LOW = True


# TIMING SETTINGS


SAMPLE_TIME_MS = 200


# POTENTIOMETER SETTINGS


POT_NOISE_THRESHOLD = 8
POT_MAX_STEP = 500


# HARDWARE SETUP

button_1 = Pin(
    BUTTON_1_GPIO,
    Pin.IN
)

button_2 = Pin(
    BUTTON_2_GPIO,
    Pin.IN
)

button_3 = Pin(
    BUTTON_3_GPIO,
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


# STATE VARIABLES


start_time_ms = time.ticks_ms()
last_sample_time_ms = time.ticks_ms()

previous_button_1 = 0
previous_button_2 = 0
previous_button_3 = 0

button_1_count = 0
button_2_count = 0
button_3_count = 0
total_button_presses = 0

previous_pot_raw = None
total_pot_activity = 0



# HELPER FUNCTIONS


def read_button(button):
    value = button.value()

    if BUTTON_ACTIVE_LOW:
        return 1 if value == 0 else 0

    return 1 if value == 1 else 0


def read_potentiometer():
    global previous_pot_raw
    global total_pot_activity

    pot_raw = pot.read()

    if previous_pot_raw is None:
        pot_delta = 0

    else:
        raw_delta = abs(
            pot_raw - previous_pot_raw
        )

        if raw_delta <= POT_NOISE_THRESHOLD:
            pot_delta = 0

        else:
            pot_delta = min(
                raw_delta,
                POT_MAX_STEP
            )

    previous_pot_raw = pot_raw
    total_pot_activity += pot_delta

    return pot_raw, pot_delta



# STARTUP



time.sleep(2)


# MAIN LOOP


while True:
    now_ms = time.ticks_ms()

    if (
            time.ticks_diff(
                now_ms,
                last_sample_time_ms
            )
            >= SAMPLE_TIME_MS
    ):
        last_sample_time_ms = now_ms

        elapsed_time_s = round(
            time.ticks_diff(
                now_ms,
                start_time_ms
            ) / 1000.0,
            2
        )

        button_1_pressed = read_button(
            button_1
        )

        button_2_pressed = read_button(
            button_2
        )

        button_3_pressed = read_button(
            button_3
        )

        if (
                button_1_pressed
                and not previous_button_1
        ):
            button_1_count += 1
            total_button_presses += 1

        if (
                button_2_pressed
                and not previous_button_2
        ):
            button_2_count += 1
            total_button_presses += 1

        if (
                button_3_pressed
                and not previous_button_3
        ):
            button_3_count += 1
            total_button_presses += 1

        previous_button_1 = button_1_pressed
        previous_button_2 = button_2_pressed
        previous_button_3 = button_3_pressed

        pot_raw, pot_delta = read_potentiometer()

        data = {
            "time_s": elapsed_time_s,

            "button_1": button_1_pressed,
            "button_2": button_2_pressed,
            "button_3": button_3_pressed,

            "button_1_count": button_1_count,
            "button_2_count": button_2_count,
            "button_3_count": button_3_count,

            "total_button_presses": total_button_presses,

            "pot_raw": pot_raw,
            "pot_delta": pot_delta,
            "total_pot_activity": total_pot_activity
        }

        # DataFoundry reads one JSON object per serial line.
        print(
            json.dumps(data)
        )
