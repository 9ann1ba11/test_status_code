import json
import time
from pymodbus.client import ModbusSerialClient
import os
from datetime import datetime
from flask import Flask, render_template_string
import threading

# Глобальные переменные для обмена данными между потоками
current_results = []
last_update_time = ""


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def read_register(client, address):
    try:
        address = int(address)
        print(f"Попытка чтения регистра {address}...")
        result = client.read_holding_registers(address)
        if result and not result.isError():
            print(f"Успешно прочитан регистр {address}: {hex(result.registers[0])}")
            return hex(result.registers[0])
        else:
            print(f"Ошибка чтения регистра {address}: {result}")
            return None
    except Exception as e:
        print(f"Исключение при чтении регистра {address}: {e}")
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

        # Обратное соответствие название -> код
        self.state_to_code = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        """Строит обратное соответствие название состояния -> код"""
        for code, name in self.status_masks_device.items():
            self.state_to_code[name] = hex(code)
        for code, name in self.status_masks_actuator.items():
            self.state_to_code[name] = hex(code)
        for code, name in self.status_masks_sec_zone.items():
            self.state_to_code[name] = hex(code)
        for code, name in self.status_masks_fire_zone.items():
            self.state_to_code[name] = hex(code)

    def create_checklist_from_config(self, addresses):
        """Создает чек-лист на основе конфигурации"""
        checklist = []

        # Приборы
        device_keys = [key for key in addresses.keys()
                       if "device" in key and addresses[key] and addresses[key].strip()]
        for key in device_keys:
            section_name = f'Прибор "{key}"'
            for code, description in self.status_masks_device.items():
                checklist.append((section_name, description, hex(code)))

        # Исполнительные устройства
        actuator_keys = [key for key in addresses.keys()
                         if "actuator" in key and addresses[key] and addresses[key].strip()]
        for key in actuator_keys:
            section_name = f'Исполнительное устройство "{key}"'
            for code, description in self.status_masks_actuator.items():
                checklist.append((section_name, description, hex(code)))

        # Охранные зоны
        security_keys = [key for key in addresses.keys()
                         if "security_zone" in key and addresses[key] and addresses[key].strip()]
        for key in security_keys:
            section_name = f'Охранная зона "{key}"'
            for code, description in self.status_masks_sec_zone.items():
                checklist.append((section_name, description, hex(code)))

        # Пожарные зоны
        fire_keys = [key for key in addresses.keys()
                     if "fire_zone" in key and addresses[key] and addresses[key].strip()]
        for key in fire_keys:
            section_name = f'Пожарная зона "{key}"'
            for code, description in self.status_masks_fire_zone.items():
                checklist.append((section_name, description, hex(code)))

        return checklist

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


# Web интерфейс
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2">
    <title>Тестирование R3-МС-КП</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 { 
            color: #366092; 
            text-align: center;
            margin-bottom: 30px;
        }
        table { 
            border-collapse: collapse; 
            width: 100%; 
            margin-bottom: 20px;
        }
        th, td { 
            border: 1px solid #ddd; 
            padding: 12px; 
            text-align: left; 
        }
        th { 
            background-color: #366092; 
            color: white; 
            font-weight: bold;
        }
        .success { 
            background-color: #d4edda; 
        }
        .fail { 
            background-color: #f8d7da; 
        }
        .header { 
            background-color: #fff3cd; 
            font-weight: bold;
            font-size: 1.1em;
        }
        .status {
            text-align: center;
            padding: 10px;
            background-color: #e9ecef;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .section {
            margin-bottom: 30px;
        }
        .section h2 {
            color: #495057;
            border-bottom: 2px solid #366092;
            padding-bottom: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Тестирование R3-МС-КП</h1>

        <div class="status">
            <strong>Последнее обновление:</strong> {{ time }} | 
            <strong>Всего состояний:</strong> {{ total_states }} | 
            <strong>Обнаружено:</strong> <span style="color: green">{{ active_states }}</span> | 
            <strong>Ожидание:</strong> <span style="color: red">{{ inactive_states }}</span>
        </div>

        {% for section in sections %}
        <div class="section">
            <h2>{{ section.name }}</h2>
            <table>
                <thead>
                    <tr>
                        <th>Состояние прибора</th>
                        <th>Ожидаемый код</th>
                        <th>Полученный код</th>
                        <th>Результат</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in section.rows %}
                    <tr class="{{ 'success' if row.result == '✅' else 'fail' if row.result == '❌' else 'header' }}">
                        <td>{{ row.state }}</td>
                        <td>{{ row.expected }}</td>
                        <td>{{ row.actual }}</td>
                        <td>{{ row.result }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endfor %}

        <div style="text-align: center; color: #6c757d; margin-top: 30px;">
            Авто-обновление каждые 2 секунды
        </div>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    global current_results, last_update_time

    # Группируем результаты по секциям
    sections = {}
    for row in current_results:
        section_name = row['section']
        if section_name not in sections:
            sections[section_name] = []
        sections[section_name].append(row)

    # Преобразуем в список для шаблона
    section_list = []
    for section_name, rows in sections.items():
        section_list.append({
            'name': section_name,
            'rows': rows
        })

    # Статистика
    total_states = len(current_results)
    active_states = sum(1 for row in current_results if row['result'] == '✅')
    inactive_states = total_states - active_states

    return render_template_string(HTML_TEMPLATE,
                                  sections=section_list,
                                  time=last_update_time,
                                  total_states=total_states,
                                  active_states=active_states,
                                  inactive_states=inactive_states)


def start_web_server():
    """Запускает веб-сервер в отдельном потоке"""
    print("🚀 Запуск веб-сервера на http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


def initialize_checklist(decoder, addresses):
    """Инициализирует чек-лист на основе конфига"""
    global current_results
    checklist = decoder.create_checklist_from_config(addresses)

    current_results = []
    for section_name, state_name, expected_code in checklist:
        current_results.append({
            'section': section_name,
            'state': state_name,
            'expected': expected_code,
            'actual': '',
            'result': '❌'
        })


def update_web_results(current_states, decoder):
    """Обновляет результаты для веб-интерфейса"""
    global current_results, last_update_time

    # Собираем все активные состояния
    active_states = set()
    for device_type in current_states.values():
        for states_list in device_type.values():
            active_states.update(states_list)

    # Обновляем результаты
    for result in current_results:
        state_name = result['state']
        if state_name in active_states:
            result['actual'] = decoder.state_to_code.get(state_name, 'N/A')
            result['result'] = '✅'
        else:
            result['actual'] = ''
            result['result'] = '❌'

    last_update_time = datetime.now().strftime('%H:%M:%S')


def main():
    cfg = load_config()

    port = cfg.get("com_port", "COM3")
    baud = cfg.get("baudrate", 9600)
    unit_id = cfg.get("unit_id", 1)
    addresses = cfg["address"]

    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    print(f"🔧 Настройки подключения:")
    print(f"  Порт: {port}")
    print(f"  Скорость: {baud} бод")
    print(f"  Unit ID: {unit_id}")
    print(f"  Адреса: {addresses}")

    client = ModbusSerialClient(
        port=port,
        stopbits=1,
        bytesize=8,
        baudrate=baud,
        timeout=1,  # Увеличенный таймаут
        retries=1,  # Уменьшенное количество попыток
        parity="N"
    )

    print(f"🔌 Попытка подключения к COM-порту: {port}")
    
    if not client.connect():
        print("❌ Ошибка: не удалось открыть COM-порт:", port)
        return

    print("✅ Подключение к COM-порту успешно установлено")

    decoder = StatusDecoder()

    # Инициализируем чек-лист
    initialize_checklist(decoder, addresses)

    print("✅ Веб-интерфейс доступен по адресу: http://localhost:5000")
    print("📡 Запуск мониторинга устройств...")

    try:
        while True:
            current_states = {
                'device': {},
                'actuator': {},
                'security': {},
                'fire': {}
            }

            # Читаем состояния приборов
            device_keys = [key for key in addresses.keys()
                           if "device" in key and addresses[key] and addresses[key].strip()]
            for key in device_keys:
                code = read_register(client, addresses[key])
                if code:
                    codes = decoder.decode_device(code)
                    current_states['device'][key] = codes
                    print(f"Прибор ({key} - {addresses[key]}): {codes}")

            # Читаем состояния ИУ
            actuator_keys = [key for key in addresses.keys()
                             if "actuator" in key and addresses[key] and addresses[key].strip()]
            for key in actuator_keys:
                code = read_register(client, addresses[key])
                if code:
                    codes = decoder.decode_actuator(code)
                    current_states['actuator'][key] = codes
                    print(f"ИУ ({key} - {addresses[key]}): {codes}")

            # Читаем состояния охранных зон
            security_keys = [key for key in addresses.keys()
                             if "security_zone" in key and addresses[key] and addresses[key].strip()]
            for key in security_keys:
                code = read_register(client, addresses[key])
                if code:
                    codes = decoder.decode_sec_zone(code)
                    current_states['security'][key] = codes
                    print(f"Охранная зона ({key} - {addresses[key]}): {codes}")

            # Читаем состояния пожарных зон
            fire_keys = [key for key in addresses.keys()
                         if "fire_zone" in key and addresses[key] and addresses[key].strip()]
            for key in fire_keys:
                code = read_register(client, addresses[key])
                if code:
                    codes = decoder.decode_fire_zone(code)
                    current_states['fire'][key] = codes
                    print(f"Пожарная зона ({key} - {addresses[key]}): {codes}")

            # Обновляем веб-интерфейс
            update_web_results(current_states, decoder)

            print("---")
            time.sleep(2)
            os.system('cls' if os.name == 'nt' else 'clear')

    except KeyboardInterrupt:
        print("\n🛑 Остановлено пользователем")
        print("🌐 Веб-интерфейс продолжает работать")

    finally:
        client.close()


if __name__ == "__main__":
    main()