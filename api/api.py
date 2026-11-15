"""API REST de dados abertos da estação (FastAPI + InfluxDB 2.x).

Endpoints:
  GET /api/dados?inicio=2026-01-01&fim=2026-01-31&agregacao=1h   -> JSON
  GET /api/export.csv?inicio=...&fim=...&agregacao=1h            -> CSV
  GET /api/ultimo                                                -> última medição
  GET /                                                          -> painel web
"""
import csv, io, os, re
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from influxdb_client import InfluxDBClient

URL, ORG = os.environ["INFLUX_URL"], os.environ["INFLUX_ORG"]
TOKEN, BUCKET = os.environ["INFLUX_TOKEN"], os.environ.get("INFLUX_BUCKET", "qualidade_ar")
CAMPOS = ["pm25", "pm10", "pm25_raw", "pm10_raw", "temperatura", "humidade", "pressao"]

app = FastAPI(title="Estação ambiental de Amora — Dados Abertos (CC BY 4.0)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
cliente = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
consulta = cliente.query_api()


def _iso(txt: str, fim: bool = False) -> str:
    try:
        d = datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Data inválida; usar AAAA-MM-DD ou AAAA-MM-DDTHH:MM")
    if fim and len(txt) == 10:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _dados(inicio: str, fim: str, agregacao: str):
    if not re.fullmatch(r"\d+[mhd]", agregacao):
        raise HTTPException(400, "agregacao deve ser do tipo 10m, 1h ou 1d")
    filtro = " or ".join(f'r._field == "{c}"' for c in CAMPOS)
    flux = f'''
    from(bucket: "{BUCKET}")
      |> range(start: {_iso(inicio)}, stop: {_iso(fim, True)})
      |> filter(fn: (r) => r._measurement == "qualidade_ar" and ({filtro}))
      |> aggregateWindow(every: {agregacao}, fn: mean, createEmpty: false)
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumns: "_value")
      |> sort(columns: ["_time"])'''
    linhas = []
    for tabela in consulta.query(flux):
        for r in tabela.records:
            linha = {"tempo_utc": r["_time"].strftime("%Y-%m-%dT%H:%M:%SZ")}
            for c in CAMPOS:
                v = r.values.get(c)
                linha[c] = None if v is None else round(v, 2)
            linhas.append(linha)
    return linhas


@app.get("/api/dados")
def dados(inicio: str = Query(...), fim: str = Query(...), agregacao: str = "1h"):
    return _dados(inicio, fim, agregacao)


@app.get("/api/export.csv")
def exportar(inicio: str = Query(...), fim: str = Query(...), agregacao: str = "1h"):
    linhas = _dados(inicio, fim, agregacao)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["tempo_utc"] + CAMPOS)
    w.writeheader()
    w.writerows(linhas)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=estacao_amora.csv"})


@app.get("/api/ultimo")
def ultimo():
    agora = datetime.now(timezone.utc)
    linhas = _dados((agora - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
                    agora.strftime("%Y-%m-%dT%H:%M"), "1m")
    if not linhas:
        raise HTTPException(404, "Sem dados nas últimas 3 horas")
    return linhas[-1]


app.mount("/", StaticFiles(directory="web", html=True), name="web")
