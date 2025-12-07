import asyncio
import threading
import sys
from bleak import BleakScanner, BleakClient

RX_UUID = "12345678-1234-5678-1234-56789abcdef0"
TARGET_NAME = "EBikeSensor"

pas_field = "0"
speed_field = "0"
range_field = "0"
dist_field = "0"

client = None
loop = asyncio.new_event_loop()
ble_running = True
connected_event = threading.Event()

HELP_TEXT = """
Commands:
  tx <message>         - send raw text to the Pico
  set pas|speed|range|dist <value>
                      - update CSV fields
  fields               - print current PAS/SPEED/RANGE/DIST values
  send                 - transmit CSV payload (pas,speed,range,dist)
  wait                 - block until the BLE link is ready
  help                 - show this help text
  quit                 - exit the program
"""


def set_status(msg: str) -> None:
    print(f"[STATUS] {msg}")


async def ble_worker():
    global client, ble_running

    try:
        while ble_running:
            set_status("Scanning for EBikeSensor...")
            device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name and TARGET_NAME in d.name
            )

            if device:
                break

            if not ble_running:
                return

            set_status("Device not found. Retrying in 5 seconds...")
            await asyncio.sleep(5)

        if not ble_running:
            return

        set_status(f"Connecting to {device.address}...")
        client = BleakClient(device.address)
        await client.connect()
        set_status("Connected. Ready to send data.")
        connected_event.set()

        while ble_running:
            await asyncio.sleep(1)

    except Exception as exc:
        set_status(f"BLE error: {exc}")
    finally:
        connected_event.clear()
        if client and client.is_connected:
            await client.disconnect()
            set_status("Disconnected.")
        client = None


def ble_thread_main():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_worker())
    loop.close()


threading.Thread(target=ble_thread_main, daemon=True).start()


def sanitize_float(value: str) -> str:
    try:
        return f"{float(value)}"
    except ValueError:
        return "0"


def print_fields():
    print(f"PAS: {pas_field}")
    print(f"SPD: {speed_field}")
    print(f"RNG: {range_field}")
    print(f"DST: {dist_field}")


def require_client() -> bool:
    if client:
        return True
    print("Not connected yet. Use 'wait' or try again after connection completes.")
    return False


def send_payload(payload: str) -> None:
    if not require_client():
        return

    future = asyncio.run_coroutine_threadsafe(
        client.write_gatt_char(RX_UUID, payload.encode()),
        loop
    )
    try:
        future.result(timeout=5)
        set_status(f"Sent: {payload}")
    except Exception as exc:
        set_status(f"Send failed: {exc}")


def print_help():
    print(HELP_TEXT.strip())


print("E-Bike BLE TX Terminal (send-only)")
print_help()


def shutdown():
    global ble_running
    ble_running = False
    connected_event.set()
    try:
        loop.call_soon_threadsafe(lambda: None)
    except RuntimeError:
        pass


try:
    while True:
        user_input = input("> ").strip()

        if not user_input:
            continue

        if user_input == "quit":
            print("Exiting...")
            break

        if user_input == "help":
            print_help()
            continue

        if user_input == "wait":
            print("Waiting for BLE connection...")
            connected_event.wait()
            if client:
                print("Connected.")
            continue

        if user_input == "fields":
            print_fields()
            continue

        if user_input == "send":
            payload = ",".join(
                [
                    pas_field.strip() or "0",
                    sanitize_float(speed_field.strip()),
                    sanitize_float(range_field.strip()),
                    sanitize_float(dist_field.strip()),
                ]
            )
            send_payload(payload)
            continue

        if user_input.startswith("tx "):
            message = user_input[3:].strip()
            if not message:
                print("Usage: tx <message>")
                continue
            send_payload(message)
            continue

        if user_input.startswith("set "):
            parts = user_input.split(maxsplit=2)
            if len(parts) != 3:
                print("Usage: set pas|speed|range|dist <value>")
                continue

            field, value = parts[1], parts[2]
            if field == "pas":
                pas_field = value
            elif field == "speed":
                speed_field = value
            elif field == "range":
                range_field = value
            elif field == "dist":
                dist_field = value
            else:
                print("Unknown field. Use pas, speed, range, or dist.")
                continue

            print_fields()
            continue

        print("Unknown command. Type 'help' to see available commands.")

except KeyboardInterrupt:
    print("\nKeyboard interrupt received.")
finally:
    shutdown()

print("Shutting down...")
sys.exit()
