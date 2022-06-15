import requests

API_BASE = 'https://demo.thingsboard.io/api/v1/03I0KyQkN5mzWQhzNQZ4/telemetry'

STATIC_DATA_KEYS = [
    'SAP part number',
    'SAP serial number',
    'SAP date code',
    'SAP revision',
    'DSP FW Rev',
    'DSP FW Date',
    'Redundant MCU FW Rev',
    'Redundant MCU FW Date',
    'Display MCU FW Rev',
    'Display MCU FW Date'
]

PHASE1_DATA_KEYS = [
    'AC Voltage(Phase1)',
    'AC Current(Phase1)',
    'AC Power(Phase1)',
    'AC Frequency(Phase1)'
]

PHASE2_DATA_KEYS = [
    'AC Voltage(Phase2)',
    'AC Current(Phase2)',
    'AC Power(Phase2)',
    'AC Frequency(Phase2)'
]


PHASE3_DATA_KEYS = [
    'AC Voltage(Phase3)',
    'AC Current(Phase3)',
    'AC Power(Phase3)',
    'AC Frequency(Phase3)'
]


SOLAR1_DATA_KEYS = [
    'Solar Voltage at Input 1',
    'Solar Current at Input 1',
    'Solar Power at Input 1',
]

SOLAR2_DATA_KEYS = [
    'Solar Voltage at Input 2',
    'Solar Current at Input 2',
    'Solar Power at Input 2',
]

OTHER_KEYS = [
    'ACPower',
    '(+) Bus Voltage',
    '(-) Bus Voltage',
    'Supplied ac energy today',
    'Inverter runtime today',
    'Supplied ac energy (total)',
    'Inverter runtime (total)',
    'Calculated temperature inside rack',
    'Status AC Output 1',
    'Status AC Output 2',
    'Status AC Output 3',
    'Status AC Output 4',
    'Status DC Input 1',
    'Status DC Input 2',
    'Error Status',
    'Error Status AC 1',
    'Global Error 1',
    'CPU Error',
    'Global Error 2',
    'Limits AC output 1',
    'Limits AC output 2',
    'Global Error 3',
    'Limits DC 1',
    'Limits DC 2',
    'History status messages'
]


class ThingsBoardAPILogger:

    def __init__(self):
        pass

    def log(self, data):

        # dynamic_data = self.get_dynamic_data(data)
        url = f"{API_BASE}"
        response = requests.post(
            url,
            json=data
        )
        if response.status_code not in [200, 201]:
            print(f"Failed to post device data to thingsboard, Status: {response.status_code}")

    def get_dynamic_data(self, data):
        dynamic_data = {
            'phase-1': {
                'voltage': self.get_val(data, 'AC Voltage(Phase1)', 0.1),
                'current': self.get_val(data, 'AC Current(Phase1)', 0.01),
                'power': self.get_val(data, 'AC Power(Phase1)'),
                'frequency': self.get_val(data, 'AC Frequency(Phase1)', 0.01),
            },
            'phase-2': {
                'voltage': self.get_val(data, 'AC Voltage(Phase2)', 0.1),
                'current': self.get_val(data, 'AC Current(Phase2)', 0.01),
                'power': self.get_val(data, 'AC Power(Phase2)'),
                'frequency': self.get_val(data, 'AC Frequency(Phase2)', 0.01),
            },
            'phase-3': {
                'voltage': self.get_val(data, 'AC Voltage(Phase3)', 0.1),
                'current': self.get_val(data, 'AC Current(Phase3)', 0.01),
                'power': self.get_val(data, 'AC Power(Phase3)'),
                'frequency': self.get_val(data, 'AC Frequency(Phase3)', 0.01),
            },
            'solar-1': {
                'voltage': self.get_val(data, 'Solar Voltage at Input 1', 0.1),
                'current': self.get_val(data, 'Solar Current at Input 1', 0.01),
                'power': self.get_val(data, 'Solar Power at Input 1'),
            },
            'solar-2': {
                'voltage': self.get_val(data, 'Solar Voltage at Input 2', 0.1),
                'current': self.get_val(data, 'Solar Current at Input 2', 0.01),
                'power': self.get_val(data, 'Solar Power at Input 2'),
            },
            'inverter': {
                'power': self.get_val(data, 'ACPower'),
                'energy': self.get_val(data, 'Supplied ac energy (total)', 3600000.0),
                'runtime': self.get_val(data, 'Inverter runtime (total)'),
                'temperature': self.get_val(data, 'Calculated temperature inside rack'),
            }
        }
        return dynamic_data

    def get_val(self, data, key, divisor=None):
        val = data.get(key)
        if val is not None and divisor is not None:
            val = val * divisor
        return val