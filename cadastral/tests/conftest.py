"""
Konfigurasjon og delte fixtures for cadastral-tester.

Mocker kartverketsAPI._create_context for å unngå ekte SOAP-kall mot grunnbok.no
under oppstart av klassen.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

from kartverkets_api.kartverket import kartverketsAPI


def _make_api_instance() -> kartverketsAPI:
    """
    Instansierer kartverketsAPI med _create_context mocka slik at
    ingen ekte nettverkskall blir gjort mot grunnbok.no.
    """
    with patch.dict(os.environ, {"GRUNNBOK_USERNAME": "test_user", "GRUNNBOK_PASSWORD": "test_pass"}):
        with patch.object(kartverketsAPI, "_create_context", return_value=MagicMock()):
            instance = kartverketsAPI()

    instance.logger = MagicMock()
    return instance


@pytest.fixture
def api() -> kartverketsAPI:
    return _make_api_instance()
