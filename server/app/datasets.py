"""Validación de CSV antes de aceptarlos (§10: tipo, tamaño y contenido) y perfil del objetivo.

Usa solo la librería estándar: la API no carga pandas ni TensorFlow, así queda liviana.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass

from app.config import settings

MAX_ROWS = 5000
MAX_COLUMNS = 60
MAX_CATEGORIES = 20
MAX_CLASSES = 10
MISSING = {"", "na", "nan", "null", "none", "?"}


class DatasetRejected(ValueError):
    """El archivo no cumple las reglas; el mensaje se muestra tal cual."""


@dataclass
class CsvReport:
    rows: int
    schema: list[dict]
    checksum: str


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _kind(values: list[str]) -> str:
    present = [v for v in values if v.strip().lower() not in MISSING]
    if not present:
        return "empty"
    numbers = [_number(v) for v in present]
    if all(n is not None for n in numbers):
        return "integer" if all(float(n).is_integer() for n in numbers) else "float"
    return "categorical"


def inspect_csv(content: bytes) -> CsvReport:
    if len(content) > settings.max_upload_kb * 1024:
        raise DatasetRejected(f"El archivo supera el máximo de {settings.max_upload_kb} KB.")
    if b"\x00" in content[:4096]:
        raise DatasetRejected("El archivo parece binario; solo se aceptan CSV de texto.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetRejected("El archivo no está en UTF-8.") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise DatasetRejected("El CSV necesita encabezados y al menos una fila de datos.")
    headers = [h.strip() for h in rows[0]]
    if len(headers) < 2:
        raise DatasetRejected("Se necesitan al menos dos columnas: características y objetivo.")
    if len(headers) > MAX_COLUMNS:
        raise DatasetRejected(f"Máximo {MAX_COLUMNS} columnas en esta versión.")
    if any(not h for h in headers):
        raise DatasetRejected("Hay columnas sin nombre en el encabezado.")
    if len(set(headers)) != len(headers):
        raise DatasetRejected("Hay nombres de columna repetidos.")
    data = rows[1:]
    if len(data) < settings.min_rows:
        raise DatasetRejected(f"El CSV tiene {len(data)} filas; el mínimo es {settings.min_rows}.")
    if len(data) > MAX_ROWS:
        raise DatasetRejected(f"El CSV tiene {len(data)} filas; el máximo en esta versión es {MAX_ROWS}.")
    bad = next((i for i, row in enumerate(data, start=2) if len(row) != len(headers)), None)
    if bad is not None:
        raise DatasetRejected(f"La fila {bad} no tiene {len(headers)} columnas.")

    schema = []
    for index, name in enumerate(headers):
        values = [row[index].strip() for row in data]
        present = [v for v in values if v.lower() not in MISSING]
        schema.append({
            "name": name,
            "kind": _kind(values),
            "nulls": len(values) - len(present),
            "unique": len(set(present)),
        })
    return CsvReport(rows=len(data), schema=schema, checksum=hashlib.sha256(content).hexdigest())


def target_profile(schema: list[dict], target: str) -> dict:
    """Tipo de problema según la columna objetivo: clasificación (con N clases) o regresión."""
    column = next((c for c in schema if c["name"] == target), None)
    if column is None:
        raise ValueError(f"La columna objetivo «{target}» no existe.")
    if column["kind"] == "empty":
        raise ValueError(f"La columna «{target}» está vacía.")
    if column["kind"] == "float" or (column["kind"] == "integer" and column["unique"] > MAX_CLASSES):
        return {"task": "regression", "classes": 0}
    if column["unique"] < 2:
        raise ValueError(f"La columna «{target}» tiene un solo valor; no hay nada que aprender.")
    if column["unique"] > MAX_CLASSES:
        raise ValueError(f"La columna «{target}» tiene {column['unique']} clases; el máximo es {MAX_CLASSES}.")
    return {"task": "classification", "classes": column["unique"]}


def usable_features(schema: list[dict], target: str) -> list[dict]:
    """Columnas que entran a la red: numéricas, o de texto con pocas categorías."""
    return [
        c for c in schema
        if c["name"] != target and c["kind"] != "empty"
        and (c["kind"] != "categorical" or c["unique"] <= MAX_CATEGORIES)
    ]


def input_width(schema: list[dict], target: str) -> int:
    """Neuronas de entrada: una por columna numérica y una por categoría (one-hot)."""
    return sum(c["unique"] if c["kind"] == "categorical" else 1 for c in usable_features(schema, target))
