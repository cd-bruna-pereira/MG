import asyncio
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

import asyncpg
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .arduino_connection import ArduinoConnection
from .arduino_handler import ArduinoHandler
from .calculo_concentracao import calcular_concentracao_h2, calcular_concentracao_o2

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")


class LeituraGas(BaseModel):
    date_time: datetime
    concentracao_h2: float
    concentracao_o2: float
    temperatura: float
    umidade: float
    pressao: float


class ArduinoPortSelection(BaseModel):
    port: str


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: str) -> None:
        disconnected = []
        for connection in tuple(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


async def parar_tarefa_arduino(app: FastAPI) -> None:
    task = app.state.reader_task
    if task.done():
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error:
            logger.error("A tarefa anterior do Arduino terminou com erro.", exc_info=error)
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Erro ao encerrar a tarefa anterior do Arduino.")


async def ler_arduino_continuamente(app: FastAPI, requested_port: str | None = None) -> None:
    app.state.arduino_status.update(connected=False, port=None, error=None)
    if not DATABASE_URL:
        app.state.arduino_status["error"] = "DATABASE_URL não configurada"
        logger.warning("DATABASE_URL não configurada; leitura do Arduino desativada.")
        return
    connection = ArduinoConnection()
    port = requested_port or connection.detect_arduino_port()
    if not port:
        app.state.arduino_status["error"] = "Nenhuma porta serial detectada"
        logger.warning("Arduino não detectado; API iniciada sem coleta automática.")
        return
    app.state.arduino_status["port"] = port
    if not connection.connect(port):
        app.state.arduino_status["error"] = f"Não foi possível abrir a porta {port}"
        logger.warning("Não foi possível abrir a porta serial %s.", port)
        return

    handler = ArduinoHandler(connection)
    app.state.arduino_status.update(connected=True, error=None)
    logger.info("Arduino conectado na porta %s.", port)
    try:
        while True:
            if handler.is_connected():
                raw = handler.read_sensor_data()
                if raw:
                    try:
                        record = handler.get_dataframe_format(raw)
                        h2 = calcular_concentracao_h2(record["H2_Raw"])
                        o2 = calcular_concentracao_o2(h2)
                        now = datetime.now()
                        values = (now, h2, o2, record["Ambient_Temp"], record["Ambient_Hum"], record["Ambient_Pressure"])
                        if not all(math.isfinite(float(value)) for value in values[1:]):
                            app.state.arduino_status["error"] = "Leitura recebida sem todos os valores dos sensores"
                            logger.warning("Leitura ignorada por conter valores inválidos: %s", raw)
                            await asyncio.sleep(1)
                            continue
                        async with app.state.db.acquire() as db:
                            await db.execute(
                                "INSERT INTO leituras_gas (date_time, concentracao_h2, concentracao_o2, temperatura, umidade, pressao) VALUES ($1, $2, $3, $4, $5, $6)",
                                *values,
                            )
                        await manager.broadcast(json.dumps(dict(zip(
                            ("date_time", "concentracao_h2", "concentracao_o2", "temperatura", "umidade", "pressao"),
                            values,
                        )), default=str))
                        app.state.arduino_status["last_reading"] = now.isoformat()
                        app.state.arduino_status["error"] = None
                    except (asyncpg.PostgresError, TypeError, ValueError) as exc:
                        app.state.arduino_status["error"] = f"Erro ao processar leitura: {exc}"
                        logger.exception("Erro ao processar leitura do Arduino.")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    finally:
        app.state.arduino_status["connected"] = False
        connection.disconnect()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DATABASE_URL:
        raise RuntimeError("Defina DATABASE_URL antes de iniciar o backend.")
    app.state.arduino_status = {
        "connected": False,
        "port": None,
        "last_reading": None,
        "error": None,
    }
    app.state.arduino_lock = asyncio.Lock()
    app.state.db = await asyncpg.create_pool(DATABASE_URL)
    app.state.reader_task = asyncio.create_task(ler_arduino_continuamente(app))
    try:
        yield
    finally:
        await parar_tarefa_arduino(app)
        await app.state.db.close()


app = FastAPI(title="Monitoramento de Gás", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/arduino/status")
async def arduino_status() -> dict[str, object]:
    return app.state.arduino_status


@app.get("/api/arduino/ports")
async def arduino_ports() -> list[dict[str, str]]:
    return ArduinoConnection().list_available_ports()


@app.post("/api/arduino/connect")
async def connect_arduino(selection: ArduinoPortSelection) -> dict[str, object]:
    available_ports = {item["device"] for item in ArduinoConnection().list_available_ports()}
    if selection.port not in available_ports:
        raise HTTPException(status_code=400, detail="A porta selecionada não está disponível.")

    async with app.state.arduino_lock:
        await parar_tarefa_arduino(app)
        app.state.reader_task = asyncio.create_task(
            ler_arduino_continuamente(app, selection.port)
        )
        await asyncio.sleep(0.1)
    return app.state.arduino_status


@app.post("/api/arduino/disconnect")
async def disconnect_arduino() -> dict[str, object]:
    async with app.state.arduino_lock:
        await parar_tarefa_arduino(app)
        app.state.arduino_status.update(
            connected=False,
            port=None,
            last_reading=None,
            error="Desconectado pelo usuário",
        )
    return app.state.arduino_status


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/leituras", status_code=201)
async def registrar_leitura_manual(leitura: LeituraGas) -> dict[str, str]:
    try:
        async with app.state.db.acquire() as db:
            await db.execute(
                "INSERT INTO leituras_gas (date_time, concentracao_h2, concentracao_o2, temperatura, umidade, pressao) VALUES ($1, $2, $3, $4, $5, $6)",
                leitura.date_time, leitura.concentracao_h2, leitura.concentracao_o2,
                leitura.temperatura, leitura.umidade, leitura.pressao,
            )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=400, detail="Uma leitura com este timestamp exato já existe.") from exc
    return {"mensagem": "Leitura registrada com sucesso"}


@app.get("/api/leituras", response_model=List[LeituraGas])
async def consultar_leituras(
    inicio: datetime = Query(...),
    fim: datetime = Query(...),
) -> list[LeituraGas]:
    if inicio > fim:
        raise HTTPException(status_code=400, detail="O início deve ser anterior ao fim.")
    async with app.state.db.acquire() as db:
        registros = await db.fetch(
            "SELECT date_time, concentracao_h2, concentracao_o2, temperatura, umidade, pressao FROM leituras_gas WHERE date_time >= $1 AND date_time <= $2 ORDER BY date_time ASC",
            inicio,
            fim,
        )
    return [LeituraGas(**dict(registro)) for registro in registros]
