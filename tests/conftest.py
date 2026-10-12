import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings  # noqa: E402


VARIABLES_DE_ENTORNO = ("DATABASE_URL", "SALIDA_SILENCIOSA", "CLAVE_CIFRADO", "IOL_LIVE_TRADING",
                        "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "IOL_USERNAME", "IOL_PASSWORD")


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    """Los tests nunca tocan una base, Telegram ni IOL reales aunque la PC tenga esas variables."""
    for nombre in VARIABLES_DE_ENTORNO:
        monkeypatch.delenv(nombre, raising=False)


@pytest.fixture
def base_sqlite(tmp_path, monkeypatch):
    """Activa el modo base de datos contra un SQLite temporal con las tablas del esquema."""
    from src import db
    url = f"sqlite:///{(tmp_path / 'base.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    motor = db.motor()
    db.crear_tablas()
    yield motor
    motor.dispose()


@pytest.fixture
def settings():
    return load_settings(usuario=Path(__file__).parent / "_sin_preferencias.yaml")  # tests sin prefs del usuario


def serie(drift: float, n: int = 400, seed: int = 0, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = drift + rng.normal(0, vol, n)
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = 10 * np.exp(np.cumsum(r))
    return pd.DataFrame({"close": close, "volume": rng.integers(1e4, 1e5, n)}, index=idx)
