#!/usr/bin/python3
# -*- coding: utf-8 -*-
import binascii
import struct


def ma_mi(data):
    ma, mi = struct.unpack('>BB', data)
    return '{:02d}.{:02d}'.format(ma, mi)

# Variables in the data-block of a Delta RPI M-series inverter,
# as far as I've been able to establish their meaning.
# The fields for each variable are as follows:
# name, struct, size in bytes, decoder, multiplier-exponent
# (10^x), unit, SunSpec equivalent


DELTA_RPI_DATA = (
    ("SAP part number", "11s", str),
    ("SAP serial number", "13s", str),
    ("SAP date code", "4s", binascii.hexlify),
    ("SAP revision", "2s", binascii.hexlify),
    ("DSP FW Rev", "2s", ma_mi, 0, "MA,MI"),
    ("DSP FW Date", "2s", ma_mi, 0, "MA,MI"),
    ("Redundant MCU FW Rev", "2s", ma_mi, 0, "MA,MI"),
    ("Redundant MCU FW Date", "2s", ma_mi, 0, "MA,MI"),
    ("Display MCU FW Rev", "2s", ma_mi, 0, "MA,MI"),
    ("Display MCU FW Date", "2s", ma_mi, 0, "MA,MI"),
    ("Display WebPage Ctrl FW Rev", "2s", ma_mi, 0, "MA,MI"),
    ("Display WebPage Ctrl FW Date", "2s", ma_mi, 0, "MA,MI"),
    ("Display WiFi Ctrl FW Rev", "2s", ma_mi, 0, "MA,MI"),
    ("Display WiFi Ctrl FW Date", "2s", ma_mi, 0, "MA,MI"),
    ("AC Voltage(Phase1)", "H", float, -1, "V"),
    ("AC Current(Phase1)", "H", float, -2, "A", "AphA"),
    ("AC Power(Phase1)", "H", int, 0, "W"),
    ("AC Frequency(Phase1)", "H", float, -2, "Hz"),
    ("AC Voltage(Phase1) [Redundant]", "H", float, -1, "V"),
    ("AC Frequency(Phase1) [Redundant]", "H", float, -2, "Hz"),
    ("AC Voltage(Phase2)", "H", float, -1, "V"),
    ("AC Current(Phase2)", "H", float, -2, "A", "AphB"),
    ("AC Power(Phase2)", "H", int, 0, "W"),
    ("AC Frequency(Phase2)", "H", float, -2, "Hz"),
    ("AC Voltage(Phase2) [Redundant]", "H", float, -1, "V"),
    ("AC Frequency(Phase2) [Redundant]", "H", float, -2, "Hz"),
    ("AC Voltage(Phase3)", "H", float, -1, "V"),
    ("AC Current(Phase3)", "H", float, -2, "A", "AphC"),
    ("AC Power(Phase3)", "H", int, 0, "W"),
    ("AC Frequency(Phase3)", "H", float, -2, "Hz"),
    ("AC Voltage(Phase3) [Redundant]", "H", float, -1, "V"),
    ("AC Frequency(Phase3) [Redundant]", "H", float, -2, "Hz"),
    ("Solar Voltage at Input 1", "H", float, -1, "V"),
    ("Solar Current at Input 1", "H", float, -2, "A"),
    ("Solar Power at Input 1", "H", int, 0, "W"),
    ("Solar Voltage at Input 2", "H", float, -1, "V"),
    ("Solar Current at Input 2", "H", float, -2, "A"),
    ("Solar Power at Input 2", "H", int, 0, "W"),
    ("ACPower", "H", int, 0, "W"),
    ("(+) Bus Voltage", "H", float, -1, "V"),
    ("(-) Bus Voltage", "H", float, -1, "V"),
    ("Supplied ac energy today", "I", int, 0, "Wh"),
    ("Inverter runtime today", "I", int, 0, "second"),
    ("Supplied ac energy (total)", "I", int, 0, "Wh"),
    ("Inverter runtime (total)", "I", int, 0, "second"),
    ("Calculated temperature inside rack", "h", int, 0, "°C", "TmpSnk"),
    ("Status AC Output 1", "B", int),
    ("Status AC Output 2", "B", int),
    ("Status AC Output 3", "B", int),
    ("Status AC Output 4", "B", int),
    ("Status DC Input 1", "B", int),
    ("Status DC Input 2", "B", int),
    ("Error Status", "B", int),
    ("Error Status AC 1", "B", int),
    ("Global Error 1", "B", int),
    ("CPU Error", "B", int),
    ("Global Error 2", "B", int),
    ("Limits AC output 1", "B", int),
    ("Limits AC output 2", "B", int),
    ("Global Error 3", "B", int),
    ("Limits DC 1", "B", int),
    ("Limits DC 2", "B", int),
    ("History status messages", "20s", binascii.hexlify),
)

DELTA_RPI_INFO = (
)

DELTA_RPI_DATA_STRUCT = '>' + ''.join([item[1] for item in DELTA_RPI_DATA])
DELTA_RPI_INFO_STRUCT = '>' + ''.join([item[1] for item in DELTA_RPI_INFO])
