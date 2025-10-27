import json
import time
from pymodbus.client import ModbusSerialClient


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def read_register(client, unit_id, address):
    try:
        address = int(address)
        result = client.read_holding_registers(address, 1, unit=unit_id)
        if result and result.registers:
            return result.registers[0]
        else:
            return None
    except Exception:
        return None


def main():
    cfg = load_config()

    port = cfg.get("com_port", "COM3")
    baud = cfg.get("baudrate", 9600)
    unit_id = cfg.get("unit_id", 1)

    addresses = cfg["address"]

    client = ModbusSerialClient(
        port=port,
        baudrate=baud,
        timeout=1,
        parity="N"
    )

    if not client.connect():
        print("Ошибка: не удалось открыть COM-порт:", port)
        return

    print("=== Мониторинг в реальном времени ===")
    print("CTRL+C для выхода\n")

    try:
        while True:
            if addresses.get("actuator"):
                code = read_register(client, unit_id, addresses["actuator"])
                print(f"ИУ ({addresses['actuator']}): {code}")

            if addresses.get("security_zone"):
                code = read_register(client, unit_id, addresses["security_zone"])
                print(f"Охранная зона ({addresses['security_zone']}): {code}")

            if addresses.get("fire_zone"):
                code = read_register(client, unit_id, addresses["fire_zone"])
                print(f"Пожарная зона ({addresses['fire_zone']}): {code}")

            if addresses.get("device"):
                code = read_register(client, unit_id, addresses["device"])
                print(f"Прибор ({addresses['device']}): {code}")

            print("---")
            time.sleep(1)

    except KeyboardInterrupt:
        print("Остановлено пользователем.")

    finally:
        client.close()


if __name__ == "__main__":
    main()