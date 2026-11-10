import asyncio
import json
import logging
import math
import os
from contextlib import asynccontextmanager, suppress
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


async def ler_arduino_continuamente(app: FastAPI) -> None:
    if not DATABASE_URL:
        logger.warning("DATABASE_URL não configurada; leitura do Arduino desativada.")
        return
    connection = ArduinoConnection()
    port = connection.detect_arduino_port()
    if not port or not connection.connect(port):
        logger.warning("Arduino não detectado; API iniciada sem coleta automática.")
        return

    handler = ArduinoHandler(connection)
    try:
        while True:
            if handler.is_connected():
                raw = handler.read_sensor_data()
                if raw:
                    record = handler.get_dataframe_format(raw)
                    h2 = calcular_concentracao_h2(record["H2_Raw"])
                    o2 = calcular_concentracao_o2(h2)
                    now = datetime.now()
                    values = (now, h2, o2, record["Ambient_Temp"], record["Ambient_Hum"], record["Ambient_Pressure"])
                    async with app.state.db.acquire() as db:
                        await db.execute(
                            "INSERT INTO leituras_gas (date_time, concentracao_h2, concentracao_o2, temperatura, umidade, pressao) VALUES ($1, $2, $3, $4, $5, $6)",
                            *values,
                        )
                    if all(math.isfinite(float(value)) for value in values[1:]):
                        await manager.broadcast(json.dumps(dict(zip(
                            ("date_time", "concentracao_h2", "concentracao_o2", "temperatura", "umidade", "pressao"),
                            values,
                        )), default=str))
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        raise
    finally:
        connection.disconnect()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DATABASE_URL:
        raise RuntimeError("Defina DATABASE_URL antes de iniciar o backend.")
    app.state.db = await asyncpg.create_pool(DATABASE_URL)
    app.state.reader_task = asyncio.create_task(ler_arduino_continuamente(app))
    try:
        yield
    finally:
        app.state.reader_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.reader_task
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
