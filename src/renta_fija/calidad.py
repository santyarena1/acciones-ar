"""Filtro de calidad de datos para renta fija (puro, sin I/O).

Un score alto tiene que venir de un rendimiento real, no de un dato roto. Antes de que un instrumento pueda
COMPRARSE se exige:
- TIR calculada y dentro de un rango sensato para su tipo de tasa (una TIR de 80% en un bono USD es un precio
  viejo o mal cargado, no una oportunidad).
- Precio del día: la especie que se opera (pesos) y la que se usa para la TIR (D/MEP en bonos USD) tienen que
  haber operado (volumen nominal > 0). data912 repite el último cierre aunque no haya operaciones.
- Puntas razonables: spread bid/ask de la especie en pesos menor a `spread_puntas_max`.
- Volumen efectivo mínimo (ARS) y días al vencimiento mínimos (lo que vence ya tiene TIR ruidosa).
- Términos confiables: `confianza: baja` (p.ej. base CER calibrada) no se compra.
- No estar absurdamente lejos de la curva de su familia (`spread_curva_max_pb`).
- No estar a pocos días de un pago (`dias_corte_cupon`): BYMA corta el cupón antes de la fecha de pago y el
  modelo contaría un cupón que el comprador ya no cobra (TIR inflada justo antes de cada pago).

Las reglas cuyas columnas no están en la tabla se saltean (tablas sintéticas de tests, versiones viejas).
Resultado: columnas `apto_compra` (bool) y `motivo_no_apto` (texto, None si es apto).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DEFAULTS: dict[str, Any] = {
    "tir_rango": {"usd": [-0.05, 0.30], "nominal_ars": [0.0, 1.50], "real_cer": [-0.20, 0.40]},
    "dias_min_compra": 20,
    "volumen_min_compra_ars": 2.0e7,
    "spread_puntas_max": 0.03,
    "spread_curva_max_pb": 400,
    "confianza_excluida": ["baja"],
    "exigir_operado_hoy": True,
    "dias_corte_cupon": 5,
}


def parametros(params: dict[str, Any] | None) -> dict[str, Any]:
    p = {**DEFAULTS, **((params or {}).get("calidad") or {})}
    p["tir_rango"] = {**DEFAULTS["tir_rango"], **(p.get("tir_rango") or {})}
    return p


def _agregar(motivos: list[list[str]], mascara: pd.Series, texto: str) -> None:
    for i, malo in enumerate(mascara.fillna(False).to_numpy(dtype=bool)):
        if malo:
            motivos[i].append(texto)


def _fuera_de_rango(df: pd.DataFrame, rangos: dict[str, list[float]]) -> pd.Series:
    tir = df["tir"].astype(float)
    if "tipo_tasa" not in df:
        return pd.Series(False, index=df.index)
    lo = df["tipo_tasa"].map(lambda t: rangos.get(t, [-np.inf, np.inf])[0]).astype(float)
    hi = df["tipo_tasa"].map(lambda t: rangos.get(t, [-np.inf, np.inf])[1]).astype(float)
    return tir.notna() & ((tir < lo) | (tir > hi))


def _sin_operar(df: pd.DataFrame) -> pd.Series:
    """La especie en pesos (la que se opera) o la de la TIR no operó hoy."""
    malo = pd.Series(False, index=df.index)
    for col in ("vol_nominal_ars", "vol_nominal_tir"):
        if col in df:
            malo |= df[col].fillna(0.0).astype(float) <= 0
    return malo


def reglas_de_datos(df: pd.DataFrame, params: dict[str, Any] | None = None) -> list[list[str]]:
    """Motivos de exclusión que no dependen de la curva (sirven para no ensuciar el ajuste de curvas)."""
    p = parametros(params)
    motivos: list[list[str]] = [[] for _ in range(len(df))]
    if "tir" not in df:
        return [["sin TIR"] for _ in range(len(df))]
    _agregar(motivos, df["tir"].isna(), "sin TIR")
    _agregar(motivos, _fuera_de_rango(df, p["tir_rango"]), "TIR fuera de rango (dato dudoso)")
    if p["exigir_operado_hoy"]:
        _agregar(motivos, _sin_operar(df), "sin operaciones hoy (precio viejo)")
    if "spread_puntas_ars" in df:
        _agregar(motivos, df["spread_puntas_ars"].astype(float) > p["spread_puntas_max"], "puntas muy abiertas")
    if "confianza" in df:
        excluida = set(p["confianza_excluida"])
        _agregar(motivos, df["confianza"].isin(excluida), "términos de confianza baja")
    return motivos


def reglas_de_compra(df: pd.DataFrame, params: dict[str, Any] | None = None) -> list[list[str]]:
    """Motivos que no invalidan el dato pero sí la compra (vencimiento cercano, iliquidez, fuera de curva)."""
    p = parametros(params)
    motivos: list[list[str]] = [[] for _ in range(len(df))]
    if "dias" in df:
        _agregar(motivos, df["dias"].astype(float) < p["dias_min_compra"], "vence muy pronto")
    if "dias_proximo_pago" in df and "dias" in df:
        proximo = df["dias_proximo_pago"].astype(float)
        cerca = (proximo <= p["dias_corte_cupon"]) & (proximo < df["dias"].astype(float))
        _agregar(motivos, cerca, "cerca del corte de cupón")
    if "volumen_ars" in df:
        _agregar(motivos, df["volumen_ars"].fillna(0.0).astype(float) < p["volumen_min_compra_ars"], "poco volumen")
    if "spread_vs_curva_pb" in df:
        lejos = df["spread_vs_curva_pb"].astype(float).abs() > p["spread_curva_max_pb"]
        _agregar(motivos, lejos, "muy lejos de su curva (dato dudoso)")
    return motivos


def datos_validos(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.Series:
    """True donde el dato sirve para ajustar curvas y comparar rendimientos."""
    return pd.Series([not m for m in reglas_de_datos(df, params)], index=df.index, dtype=bool)


def marcar_aptos(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Agrega `apto_compra` y `motivo_no_apto` combinando reglas de datos y de compra."""
    if df.empty:
        return df.assign(apto_compra=pd.Series(dtype=bool), motivo_no_apto=pd.Series(dtype=object))
    motivos = [a + b for a, b in zip(reglas_de_datos(df, params), reglas_de_compra(df, params))]
    return df.assign(apto_compra=[not m for m in motivos],
                     motivo_no_apto=["; ".join(m) if m else None for m in motivos])
