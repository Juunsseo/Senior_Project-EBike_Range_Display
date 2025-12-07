import uasyncio as asyncio
from epaper_driver import EPD_3in7
import framebuf

# Shared data structure, updated by main.py
sensor_data = {
    "voltage": 0.0,
    "current": 0.0,
    "power": 0.0,
    "pas": "",
    "speed": 0.0,   # km/h
    "c_range": 0.0, # km
    "dist": 0.0,    # km
    "battery": 0.0, # percentage
    "connected": False,
}

DISPLAY_WIDTH = 280
DISPLAY_HEIGHT = 480
SECTION_COUNT = 5
SECTION_HEIGHT = DISPLAY_HEIGHT // SECTION_COUNT
KM_TO_MI = 1#0.621371


def draw_big_text(fb, text, x, y, color=0x00, scale=3):
    tmp = framebuf.FrameBuffer(bytearray(8 * 8 // 8), 8, 8, framebuf.MONO_HLSB)

    for idx, ch in enumerate(text):
        tmp.fill(1)
        tmp.text(ch, 0, 0, 0)

        for yy in range(8):
            for xx in range(8):
                if tmp.pixel(xx, yy) == 0:
                    for dy in range(scale):
                        for dx in range(scale):
                            fb.pixel(
                                x + idx * 8 * scale + xx * scale + dx,
                                y + yy * scale + dy,
                                color,
                            )


def draw_centered_text(fb, text, y, color=0x00, scale=3):
    width = len(text) * 8 * scale
    x = max((DISPLAY_WIDTH - width) // 2, 0)
    draw_big_text(fb, text, x, y, color, scale)


def draw_right_aligned_text(fb, text, y, color=0x00, scale=2, margin=8):
    width = len(text) * 8 * scale
    x = max(DISPLAY_WIDTH - margin - width, 0)
    draw_big_text(fb, text, x, y, color, scale)


def draw_separator(fb, y, color=0x00, thickness=2):
    for dy in range(thickness):
        yy = y + dy
        if yy >= DISPLAY_HEIGHT:
            break
        for x in range(DISPLAY_WIDTH):
            fb.pixel(x, yy, color)


def draw_section(fb, label, value_text, top_y, *, unit_text=None, value_scale=4, unit_scale=2):
    label_scale = 2
    label_y = top_y + 6
    draw_big_text(fb, label, 10, label_y, 0x00, label_scale)

    label_height = 8 * label_scale
    value_height = 8 * value_scale
    section_bottom = top_y + SECTION_HEIGHT

    # Reserve a bit of space under the value so it sits slightly above the units.
    unit_height = 8 * unit_scale if unit_text else 0
    unit_bottom_margin = 4
    value_bottom_margin = 24

    if unit_text:
        unit_y = section_bottom - unit_height - unit_bottom_margin
    else:
        unit_y = section_bottom - unit_bottom_margin

    # Keep the value below the label but above the units.
    value_y = unit_y - value_height - 6
    min_value_y = label_y + label_height + 6
    if value_y < min_value_y:
        value_y = min_value_y

    draw_centered_text(fb, value_text, value_y, 0x00, value_scale)

    if unit_text:
        draw_right_aligned_text(fb, unit_text, unit_y, 0x00, unit_scale)


def draw_connection_status(fb, connected):
    if connected:
        draw_right_aligned_text(fb, "Connected", 4, 0x00, scale=1, margin=4)
    else:
        draw_right_aligned_text(fb, "Disconnected", 4, 0x00, scale=1, margin=4)


def _format_pas(pas_value):
    if isinstance(pas_value, (int, float)):
        return f"{int(pas_value)}"

    text = str(pas_value or "").strip()
    if not text:
        return "-"

    upper = text.upper()
    if upper.startswith("PAS"):
        stripped = text[3:].strip()
        if stripped:
            return stripped
    return text


def render_dashboard(fb, data):
    speed_kmh = data.get("speed") or 0.0
    dist_km = data.get("dist") or 0.0
    range_km = data.get("c_range") or 0.0
    battery_pct = data.get("battery")

    speed_text = f"{speed_kmh * KM_TO_MI:.1f}"
    dist_text = f"{dist_km * KM_TO_MI:.1f}"
    range_text = f"{range_km * KM_TO_MI:.1f}"
    battery_value = 0.0 if battery_pct is None else battery_pct
    battery_text = f"{battery_value:.0f}"
    pas_text = _format_pas(data.get("pas"))

    draw_connection_status(fb, bool(data.get("connected")))
    draw_section(fb, "Speed", speed_text, 0, unit_text="mph")
    draw_section(fb, "Dist. remaining", dist_text, SECTION_HEIGHT, unit_text="miles")
    draw_section(fb, "Remain range", range_text, SECTION_HEIGHT * 2, unit_text="miles")
    draw_section(fb, "Battery", battery_text, SECTION_HEIGHT * 3, unit_text="%", value_scale=4)
    draw_section(fb, "Recommended PAS", pas_text, SECTION_HEIGHT * 4, value_scale=5)

    for idx in range(1, SECTION_COUNT):
        draw_separator(fb, idx * SECTION_HEIGHT, thickness=2)


# E-ink initialization
epd = EPD_3in7()
epd.EPD_3IN7_1Gray_init()
epd.EPD_3IN7_1Gray_Clear()


async def display_task():
    """Updates the e-ink display using the minimalist dashboard layout."""
    while True:
        epd.image1Gray.fill(0xFF)
        render_dashboard(epd.image1Gray, sensor_data)
        epd.EPD_3IN7_1Gray_Display_Part(epd.buffer_1Gray)
        await asyncio.sleep(1)
