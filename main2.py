import json
import time
from pymodbus.client import ModbusSerialClient
import os

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)




def read_register(client, address):
    try:
        address = int(address)
        result = client.read_holding_registers(address)
        if result:
            return hex(result.registers[0])
        else:
            return None
    except Exception:
        return None

class StatusDecoder:
    def __init__(self):
        self.status_masks_device = {
            0x00: "Норма, отсутствие неисправностей",
            0x01: "Неисправность",
            0x02: "Пожар/Внимание", 
            0x04: "Тревога",
            0x08: "Отключен",
            0x10: "Автоматика откл",
            0x20: "Запуск СПТ",
            0x40: "Вскрытие", 
            0x80: "Неисправность питания",
            0x0200: "На охране",
            0x0400: "Обрыв АЛС",
            0x0800: "Короткое замыкание АЛС"
            
        }
        self.status_masks_actuator = {
            0x00: "Выключено, отсутствие неисправностей",
            0x01: "Включено",
            0x02: "Автоматика вкл", 
            0x04: "Неисправность",
            0x10: "Потеря связи",
            0x20: "Отсутствие 220В",
            0x40: "Отсутствие АКБ", 
            0x0200: "Заслонка ЗАКРЫТА",
            0x0400: "Заслонка ОТКРЫТА",
            0x0800: "Заслонка закрывается",
            0x1000: "Заслонка открывается"
            
        }
        self.status_masks_sec_zone = {
            0x00: "Не на охране",
            0x01: "Тревога", 
            0x02: "Задержка по входу/выходу",
            0x04: "Неудачная постановка на охрану",
            0x20: "На охране"
           
        }
        self.status_masks_fire_zone = {
            0x00: "Норма, отсутствие неисправностей",
            0x01: "Внимание", 
            0x02: "Неисправность",
            0x08: "Отключено («Обход»)",
            0x80: "Пожар"
            
        }
    
    def hex_int(self, status_value):
        if isinstance(status_value, str):
            if status_value.startswith('0x'):
                status_value = int(status_value, 16)
            else:
                status_value = int(status_value)
        return status_value

    def decode_device(self, status_value):
        active = []
        status_value = self.hex_int(status_value)

        if status_value == 0xffff:
            active.append('Неизвестно или нет связи с прибором')
        else:
        
            for mask, description in self.status_masks_device.items():
                if status_value & mask:
                    active.append(description)
        
        return active

    def decode_actuator(self, status_value):
        active = []
        status_value = self.hex_int(status_value)
        if status_value == 0xffff:
            active.append('Неизвестно или нет связи с прибором')
        else:
            for mask, description in self.status_masks_actuator.items():
                if status_value & mask:
                    active.append(description)
        
        return active

    def decode_sec_zone(self, status_value):
        active = []
        status_value = self.hex_int(status_value)
        if status_value == 0xffff:
            active.append('Неизвестно или нет связи с прибором')
        else:
            for mask, description in self.status_masks_sec_zone.items():
                if status_value & mask:
                    active.append(description)
        
        return active

    def decode_fire_zone(self, status_value):
        active = []
        status_value = self.hex_int(status_value)
        if status_value == 0xffff:
            active.append('Неизвестно или нет связи с прибором')
        else:
            for mask, description in self.status_masks_fire_zone.items():
                if status_value & mask:
                    active.append(description)
        
        return active
    
def main():
    cfg = load_config()

    port = cfg.get("com_port", "COM3")
    baud = cfg.get("baudrate", 9600)
    unit_id = cfg.get("unit_id", 1)

    addresses = cfg["address"]

    client = ModbusSerialClient(
        port=port,
        stopbits=1,
        bytesize=8,
        baudrate=baud,
        timeout=1,
        parity="N"
    )

    if not client.connect():
        print("Ошибка: не удалось открыть COM-порт:", port)
        return

    decoder = StatusDecoder()




    try:
        while True:
            
            actuator_keys = [key for key in addresses.keys() 
                            if "actuator" in key and addresses[key] and addresses[key].strip()]
            for key in actuator_keys:
                code = read_register(client, addresses[key])
                codes = decoder.decode_actuator(code)
                print(f"ИУ ({key} - {addresses[key]}): {codes}")

            
            security_keys = [key for key in addresses.keys() 
                            if "security_zone" in key and addresses[key] and addresses[key].strip()]
            for key in security_keys:
                code = read_register(client, addresses[key])
                codes = decoder.decode_sec_zone(code)
                print(f"Охранная зона ({key} - {addresses[key]}): {codes}")

            
            fire_keys = [key for key in addresses.keys() 
                        if "fire_zone" in key and addresses[key] and addresses[key].strip()]
            for key in fire_keys:
                code = read_register(client, addresses[key])
                codes = decoder.decode_fire_zone(code)
                print(f"Пожарная зона ({key} - {addresses[key]}): {codes}")

            
            device_keys = [key for key in addresses.keys() 
                          if "device" in key and addresses[key] and addresses[key].strip()]
            for key in device_keys:
                code = read_register(client, addresses[key])
                codes = decoder.decode_device(code)
                print(f"Прибор ({key} - {addresses[key]}): {codes}")

            
    # try:
    #     while True:
    #         if addresses.get("actuator"):
    #             code = read_register(client, addresses["actuator"])
    #             codes = decoder.decode_actuator(code)
    #             print(f"ИУ ({addresses['actuator']}): {codes}")

    #         if addresses.get("security_zone"):
    #             code = read_register(client, addresses["security_zone"])
    #             codes = decoder.decode_sec_zone(code)
    #             print(f"Охранная зона ({addresses['security_zone']}): {codes}")

    #         if addresses.get("fire_zone"):
    #             code = read_register(client, addresses["fire_zone"])
    #             codes = decoder.decode_fire_zone(code)
    #             print(f"Пожарная зона ({addresses['fire_zone']}): {codes}")

    #         if addresses.get("device"):
    #             code = read_register(client, addresses["device"])
    #             codes = decoder.decode_device(code)
    #             print(f"Прибор ({addresses['device']}): {codes}")

            print("---")
            time.sleep(2)
            os.system('cls' if os.name == 'nt' else 'clear')
            
            

    except KeyboardInterrupt:
        print("Остановлено пользователем.")

    finally:
        client.close()



if __name__ == "__main__":
    main()



