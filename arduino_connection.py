"""Conexão serial com Arduino."""

import serial
import serial.tools.list_ports
import time
from typing import List, Optional, Tuple


class ArduinoConnection:
    """Conexão serial com o Arduino."""
    
    def __init__(self, port: Optional[str] = None, baud_rate: int = 9600, timeout: float = 1.0):
        """Inicializa a conexão serial."""
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial_connection: Optional[serial.Serial] = None
        self.is_connected = False
    
    def list_available_ports(self) -> List[str]:
        """Lista portas seriais disponíveis."""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def detect_arduino_port(self) -> Optional[str]:
        """Tenta identificar automaticamente a porta mais provável do Arduino."""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None

        if len(ports) == 1:
            return ports[0].device

        def score(port_info) -> Tuple[int, int, str]:
            text = " ".join(
                str(value).lower()
                for value in (
                    port_info.device,
                    port_info.description,
                    port_info.manufacturer,
                    port_info.product,
                    port_info.hwid,
                )
            )

            points = 0
            keywords = ("arduino", "ch340", "ch341", "cp210", "usb serial", "ttyacm", "usbmodem")
            for keyword in keywords:
                if keyword in text:
                    points += 10

            if "ttyacm" in port_info.device.lower():
                points += 6
            if "ttyusb" in port_info.device.lower():
                points += 4

            return (points, -len(port_info.device), port_info.device)

        ranked_ports = sorted(ports, key=score, reverse=True)
        best_port = ranked_ports[0]
        return best_port.device if score(best_port)[0] > 0 else best_port.device
    
    def connect(self, port: Optional[str] = None) -> bool:
        """Conecta ao Arduino."""
        if port:
            self.port = port
        
        if not self.port:
            raise ValueError("Porta serial não especificada")
        
        try:
            # Conecta e espera o reset.
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            
            time.sleep(2)

            # Limpa buffers.
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()
            
            self.is_connected = True
            return True
            
        except serial.SerialException as e:
            print(f"Erro ao conectar na porta {self.port}: {e}")
            self.is_connected = False
            self.serial_connection = None
            return False
        except Exception as e:
            print(f"Erro inesperado ao conectar: {e}")
            self.is_connected = False
            self.serial_connection = None
            return False
    
    def disconnect(self) -> None:
        """Fecha a conexão."""
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
                self.is_connected = False
                print(f"Desconectado da porta {self.port}")
            except Exception as e:
                print(f"Erro ao desconectar: {e}")
        
        self.serial_connection = None
        self.is_connected = False
    
    def is_open(self) -> bool:
        """Retorna True se a conexão estiver aberta."""
        return self.is_connected and self.serial_connection is not None and self.serial_connection.is_open
    
    def read_line(self) -> Optional[str]:
        """Lê uma linha da serial."""
        if not self.is_open():
            return None
        
        try:
            line = self.serial_connection.readline().decode('utf-8').strip()
            return line if line else None
        except UnicodeDecodeError:
            # Fallback para latin-1.
            try:
                self.serial_connection.reset_input_buffer()
                line = self.serial_connection.readline().decode('latin-1').strip()
                return line if line else None
            except Exception:
                return None
        except Exception as e:
            print(f"Erro ao ler da porta serial: {e}")
            return None
    
    def write_command(self, command: str) -> bool:
        """Envia um comando."""
        if not self.is_open():
            return False
        
        try:
            # Garante quebra de linha.
            if not command.endswith('\n'):
                command += '\n'
            
            self.serial_connection.write(command.encode('utf-8'))
            self.serial_connection.flush()
            return True
        except Exception as e:
            print(f"Erro ao enviar comando: {e}")
            return False
    
    def flush_buffers(self) -> None:
        """Limpa buffers."""
        if self.is_open():
            try:
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
            except Exception as e:
                print(f"Erro ao limpar buffers: {e}")
    
    def __enter__(self):
        """Suporte a context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finaliza a conexão."""
        self.disconnect()
    
    def __del__(self):
        """Garante fechamento ao destruir."""
        self.disconnect()


