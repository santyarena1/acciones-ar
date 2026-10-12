import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings  # noqa: E402


@pytest.fixture
def settings():
    return load_settings()


def serie(drift: float, n: int = 400, seed: int = 0, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = drift + rng.normal(0, vol, n)
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = 10 * np.exp(np.cumsum(r))
    return pd.DataFrame({"close": close, "volume": rng.integers(1e4, 1e5, n)}, index=idx)
