"""Preparación de datos y entrenamiento con TensorFlow/Keras.

Sin pandas ni scikit-learn (memoria justa en el hosting gratuito): el preprocesamiento es
NumPy puro. Las medias, desviaciones y medianas se calculan solo con la partición de
entrenamiento, para que la prueba final mida datos que la red nunca vio.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import numpy as np

from app import datasets as ds


@dataclass
class Prepared:
    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    feature_names: list[str]
    classes: list[str] = field(default_factory=list)
    y_mean: float = 0.0
    y_std: float = 1.0
    preprocess: dict = field(default_factory=dict)


def _missing(value: str) -> bool:
    return value.strip().lower() in ds.MISSING


def _split_indices(y: np.ndarray, split: dict, seed: int, stratify: bool) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    groups = [np.flatnonzero(y == c) for c in np.unique(y)] if stratify else [np.arange(len(y))]
    train, val, test = [], [], []
    for group in groups:
        group = rng.permutation(group)
        n_test = max(1, round(len(group) * split["test"]))
        n_val = max(1, round(len(group) * split["validation"]))
        test.extend(group[:n_test])
        val.extend(group[n_test:n_test + n_val])
        train.extend(group[n_test + n_val:])
    return tuple(rng.permutation(np.array(part, dtype=int)) for part in (train, val, test))


def prepare(content: bytes, schema: list[dict], target: str, task: str, split: dict, seed: int) -> Prepared:
    text = content.decode("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    header, data = [h.strip() for h in rows[0]], rows[1:]
    t_index = header.index(target)
    data = [row for row in data if not _missing(row[t_index])]
    if len(data) < 10:
        raise ValueError("Quedan menos de 10 filas con objetivo definido.")

    # Objetivo
    raw_y = [row[t_index].strip() for row in data]
    classes: list[str] = []
    if task == "classification":
        classes = sorted(set(raw_y), key=lambda v: (float(v) if ds._number(v) is not None else float("inf"), v))
        lookup = {label: i for i, label in enumerate(classes)}
        y = np.array([lookup[v] for v in raw_y], dtype="int64")
    else:
        y = np.array([float(v) for v in raw_y], dtype="float32")

    train, val, test = _split_indices(y, split, seed, stratify=task == "classification")

    # Características: numéricas estandarizadas y categóricas en one-hot (vocabulario de todo el dataset).
    columns, names, preprocess = [], [], {"numeric": {}, "categorical": {}}
    for column in ds.usable_features(schema, target):
        index = header.index(column["name"])
        values = [row[index].strip() for row in data]
        if column["kind"] == "categorical":
            vocabulary = sorted({v for v in values if not _missing(v)})
            onehot = np.zeros((len(values), len(vocabulary)), dtype="float32")
            for r, v in enumerate(values):
                if v in vocabulary:
                    onehot[r, vocabulary.index(v)] = 1.0
            columns.append(onehot)
            names += [f"{column['name']}={v}" for v in vocabulary]
            preprocess["categorical"][column["name"]] = vocabulary
        else:
            numbers = np.array([np.nan if _missing(v) else float(v) for v in values], dtype="float32")
            median = float(np.nanmedian(numbers[train])) if np.isfinite(numbers[train]).any() else 0.0
            numbers = np.where(np.isnan(numbers), median, numbers)
            mean, std = float(numbers[train].mean()), float(numbers[train].std()) or 1.0
            columns.append(((numbers - mean) / std)[:, None])
            names.append(column["name"])
            preprocess["numeric"][column["name"]] = {"median": median, "mean": mean, "std": std}
    x = np.hstack(columns).astype("float32")

    y_mean, y_std = 0.0, 1.0
    if task == "regression":
        # La red aprende el objetivo escalado; las métricas se informan en sus unidades originales.
        y_mean, y_std = float(y[train].mean()), float(y[train].std()) or 1.0
        y = ((y - y_mean) / y_std).astype("float32")
    preprocess["target"] = {"name": target, "task": task, "classes": classes, "mean": y_mean, "std": y_std}

    return Prepared(x[train], y[train], x[val], y[val], x[test], y[test], names, classes, y_mean, y_std, preprocess)


def build_model(config: dict, input_width: int, task: str, optimizer: str, learning_rate: float):
    import keras

    model = keras.Sequential([keras.Input(shape=(input_width,))])
    for layer in config["layers"]:
        if layer["type"] == "Dense":
            model.add(keras.layers.Dense(layer["units"], activation=layer["activation"]))
        else:
            model.add(keras.layers.Dropout(layer["rate"]))
    out = config["output"]
    model.add(keras.layers.Dense(out["units"], activation=out["activation"]))

    opt = {"adam": keras.optimizers.Adam, "sgd": keras.optimizers.SGD,
           "rmsprop": keras.optimizers.RMSprop}[optimizer](learning_rate=learning_rate)
    if task == "regression":
        model.compile(optimizer=opt, loss="mse", metrics=["mae"])
    elif out["units"] == 1:
        model.compile(optimizer=opt, loss="binary_crossentropy", metrics=["accuracy"])
    else:
        model.compile(optimizer=opt, loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model


def class_weights(y_train: np.ndarray, classes: int) -> dict[int, float]:
    """Pesos "balanceados": cada clase pesa en proporción inversa a su frecuencia.

    Con 25 % de "sí", un error con un "sí" pesa unas 3 veces más que con un "no", así la red
    deja de ganar puntos diciendo siempre la respuesta mayoritaria.
    """
    counts = np.bincount(y_train.astype(int), minlength=classes)
    total = len(y_train)
    return {c: float(total / (classes * n)) if n else 0.0 for c, n in enumerate(counts)}


def positive_scores(predictions: np.ndarray) -> np.ndarray:
    """Probabilidad de la clase positiva (la segunda) en clasificación binaria."""
    return predictions.reshape(-1) if predictions.shape[1] == 1 else predictions[:, 1]


def evaluate(model, data: Prepared, task: str, threshold: float | None = None) -> dict:
    predictions = model.predict(data.x_test, verbose=0)
    if task == "regression":
        pred = predictions.reshape(-1) * data.y_std + data.y_mean
        real = data.y_test * data.y_std + data.y_mean
        error = pred - real
        ss_res, ss_tot = float((error ** 2).sum()), float(((real - real.mean()) ** 2).sum()) or 1.0
        return {"r2": 1 - ss_res / ss_tot, "mae": float(np.abs(error).mean()),
                "rmse": float(np.sqrt((error ** 2).mean())), "testRows": int(len(real))}
    binary = len(data.classes) == 2
    extra: dict = {}
    if binary:
        # El umbral decide desde qué probabilidad se avisa la clase positiva (0,5 por omisión).
        cut = 0.5 if threshold is None else threshold
        scores = positive_scores(predictions)
        labels = (scores >= cut).astype(int)
        extra = {
            "threshold": cut,
            "positiveClass": data.classes[1],
            # Real y probabilidad de cada fila de prueba: la pantalla recalcula la matriz con otro umbral sin reentrenar.
            "scores": [[int(r), round(float(s), 4)] for r, s in zip(data.y_test, scores, strict=True)],
        }
    else:
        labels = predictions.argmax(1)
    size = len(data.classes)
    matrix = np.zeros((size, size), dtype=int)
    for real, pred in zip(data.y_test, labels, strict=True):
        matrix[int(real), int(pred)] += 1
    return {"accuracy": float((labels == data.y_test).mean()), "testRows": int(len(labels)),
            "classes": data.classes, "confusion": matrix.tolist(), **extra}
