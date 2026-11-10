"""Validación de redes Feedforward en el backend (§10: el frontend no es frontera de seguridad).

Una arquitectura queda ligada a un dataset y a su columna objetivo: así la capa de entrada
y la de salida se comprueban contra los datos reales antes de gastar tiempo entrenando.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app import datasets as ds

HIDDEN_ACTIVATIONS = ("relu", "tanh", "sigmoid", "elu", "selu", "linear")
OUTPUT_ACTIVATIONS = ("softmax", "sigmoid", "linear")
MAX_LAYERS = 8


class DenseLayer(BaseModel):
    type: Literal["Dense"] = "Dense"
    units: int = Field(ge=1, le=512)
    activation: str = "relu"


class DropoutLayer(BaseModel):
    type: Literal["Dropout"]
    rate: float = Field(ge=0.0, le=0.8)


class OutputLayer(BaseModel):
    units: int = Field(ge=1, le=64)
    activation: str


class ArchitectureIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    dataset_id: str
    target: str
    layers: list[DenseLayer | DropoutLayer] = Field(min_length=1, max_length=MAX_LAYERS)
    output: OutputLayer


def expected_output(profile: dict) -> list[tuple[int, str]]:
    """Salidas válidas para el objetivo: (unidades, activación)."""
    if profile["task"] == "regression":
        return [(1, "linear")]
    if profile["classes"] == 2:
        return [(1, "sigmoid"), (2, "softmax")]
    return [(profile["classes"], "softmax")]


def describe_output(profile: dict) -> str:
    options = expected_output(profile)
    return " o ".join(f"{units} neurona{'s' if units > 1 else ''} con {act}" for units, act in options)


def validate(arch: ArchitectureIn, schema: list[dict]) -> dict:
    """Devuelve el resumen (formas, parámetros) y la lista de errores; válida si no hay errores."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        profile = ds.target_profile(schema, arch.target)
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": [], "layers": [], "totalParams": 0}

    width = ds.input_width(schema, arch.target)
    if width == 0:
        errors.append("No quedan columnas útiles como entrada además del objetivo.")

    if not any(isinstance(layer, DenseLayer) for layer in arch.layers):
        errors.append("Agrega al menos una capa Dense oculta.")
    for index, layer in enumerate(arch.layers, start=1):
        if isinstance(layer, DenseLayer) and layer.activation not in HIDDEN_ACTIVATIONS:
            errors.append(f"Capa {index}: activación «{layer.activation}» no permitida en capas ocultas.")
    if isinstance(arch.layers[0], DropoutLayer):
        warnings.append("Un Dropout justo después de la entrada descarta datos crudos; suele ir tras una Dense.")
    if arch.output.activation not in OUTPUT_ACTIVATIONS:
        errors.append(f"La salida no admite la activación «{arch.output.activation}».")
    elif (arch.output.units, arch.output.activation) not in expected_output(profile):
        errors.append(f"La salida no corresponde al objetivo «{arch.target}»: se esperaba {describe_output(profile)}.")

    shapes, previous, total = [{"name": "Entrada", "units": width, "params": 0}], width, 0
    for index, layer in enumerate(arch.layers, start=1):
        if isinstance(layer, DenseLayer):
            params = previous * layer.units + layer.units
            shapes.append({"name": f"Dense {index}", "units": layer.units, "activation": layer.activation,
                           "params": params})
            previous, total = layer.units, total + params
        else:
            shapes.append({"name": f"Dropout {index}", "units": previous, "rate": layer.rate, "params": 0})
    out_params = previous * arch.output.units + arch.output.units
    shapes.append({"name": "Salida", "units": arch.output.units, "activation": arch.output.activation,
                   "params": out_params})
    total += out_params

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "task": profile["task"],
        "classes": profile["classes"],
        "inputWidth": width,
        "layers": shapes,
        "totalParams": total,
        "expectedOutput": describe_output(profile),
    }
