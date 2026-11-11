"""Conexão serial com Arduino."""

import time
from typing import List, Optional, Tuple

import serial
import serial.tools.list_ports


class ArduinoConnection:
    def __init__(self, port: Optional[str] = None, baud_rate: int = 9600, timeout: float = 0.2):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial_connection: Optional[serial.Serial] = None

    def detect_arduino_port(self) -> Optional[str]:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None

        def score(port_info) -> Tuple[int, str]:
            text = " ".join(
                str(value).lower()
                for value in (port_info.device, port_info.description, port_info.manufacturer, port_info.product)
            )
            points = sum(keyword in text for keyword in ("arduino", "ch340", "ch341", "cp210", "usb serial", "ttyacm", "usbmodem"))
            return points, port_info.device

        return max(ports, key=score).device

    def list_available_ports(self) -> List[dict[str, str]]:
        return [
            {
                "device": port.device,
                "description": port.description or port.device,
            }
            for port in serial.tools.list_ports.comports()
        ]

    def connect(self, port: Optional[str] = None) -> bool:
        self.port = port or self.port
        if not self.port:
            return False
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            time.sleep(2)
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()
            return True
        except (serial.SerialException, OSError):
            self.serial_connection = None
            return False

    def is_open(self) -> bool:
        return self.serial_connection is not None and self.serial_connection.is_open

    def disconnect(self) -> None:
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.serial_connection = None

    def read_line(self) -> Optional[str]:
        if not self.is_open():
            return None
        try:
            line = self.serial_connection.readline().decode("utf-8").strip()
            return line or None
        except (UnicodeDecodeError, OSError, serial.SerialException):
            return None
