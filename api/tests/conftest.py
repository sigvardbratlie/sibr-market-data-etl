"""
Konfigurasjon og delte fixtures for API-tester.

Bruker importlib for å laste src/api.py direkte fordi src/api/-pakken
ellers skygger for modulen.
"""
import collections
import asyncio
import importlib.util
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Last inn src/api.py direkte (unngår at src/api/-pakken skygger) ────────
_API_FILE = Path(__file__).parent.parent / "src" / "api.py"
_spec = importlib.util.spec_from_file_location("src.api", _API_FILE)
_module = importlib.util.module_from_spec(_spec)
sys.modules["src.api"] = _module          # registrer under riktig navn
_spec.loader.exec_module(_module)         # kjør modulen (imports skjer her)

DataApi = _module.DataApi


def _make_api_instance():
    """
    Instansierer DataApi med alle eksterne avhengigheter mocka.
    Setter attributtene som ApiBase.__init__ normalt ville ha satt.
    """
    with patch("src.api.BigQuery") as MockBQ, \
         patch("src.api.SecretsManager") as MockSM, \
         patch("src.api.firestore") as MockFS, \
         patch("sibr_api.ApiBase.__init__", return_value=None):

        MockSM.return_value.get_secret.return_value = "test_api_key"
        MockBQ.return_value = MagicMock()
        MockFS.Client.return_value = MagicMock()

        instance = DataApi()

    # Attributter ApiBase.__init__ normalt setter
    instance.logger = MagicMock()
    instance.api_key = None
    instance.session = None
    instance.use_proxy = False
    instance.proxies = None
    instance.base_url = None
    instance.ok_responses = 0
    instance.fail_responses = 0
    instance.rate_limit_count = None
    instance.rate_limit_period = None
    instance.request_timestamps = collections.deque()
    instance._rate_limit_lock = asyncio.Lock()
    return instance


@pytest.fixture
def api():
    return _make_api_instance()
