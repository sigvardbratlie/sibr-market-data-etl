"""
Integrasjonstester for kartverketsAPI – HTTP-kall og async-metoder med mocka
eksterne tjenester.

Tester at search_address, decode_address og get_by_property håndterer alle
responsscenarier riktig uten å gjøre ekte nettverkskall.
"""
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Delte testdata
# ─────────────────────────────────────────────────────────────────────────────

GEONORGE_ADDRESS_RESPONSE = {
    "adresser": [
        {
            "adressetekst": "Storgata 1",
            "postnummer": "0155",
            "poststed": "OSLO",
            "kommunenummer": "0301",
            "gardsnummer": 12,
            "bruksnummer": 3,
            "festenummer": 0,
            "meterdistansetilpunkt": None,
            "representasjonspunkt": {
                "lat": 59.9139,
                "lon": 10.7522,
                "epsg": "EPSG:4258",
            },
        }
    ],
    "metadata": {"sokeStreng": "Storgata 1", "totaltAntallTreff": 1},
}

NOMINATIM_RESPONSE = [
    {"lat": "59.9139", "lon": "10.7522", "display_name": "Oslo, Norge"}
]


def _mock_http_response(status_code=200, json_data=None):
    """Lager en mock-respons for requests.get."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    # Gjør mock truthy slik at `if response:` passerer
    mock_resp.__bool__ = lambda self: True
    return mock_resp


# ─────────────────────────────────────────────────────────────────────────────
# search_address
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchAddress:
    def test_address_search_returns_dict_on_200(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp):
            result = api.search_address(address="Storgata 1, Oslo", search_type="address")
        assert isinstance(result, dict)
        assert "adresser" in result

    def test_coordinates_search_returns_dict_on_200(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp):
            result = api.search_address(lat=59.9139, lon=10.7522, search_type="coordinates")
        assert isinstance(result, dict)

    def test_404_response_returns_none(self, api, capsys):
        mock_resp = _mock_http_response(404, None)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp):
            result = api.search_address(address="Finnes ikke gate", search_type="address")
        assert result is None

    def test_invalid_search_type_raises_type_error(self, api):
        with pytest.raises(TypeError):
            api.search_address(address="Storgata 1", search_type="ugyldig")

    def test_address_url_contains_sok_endpoint(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp) as mock_get:
            api.search_address(address="Storgata 1", search_type="address")
        called_url = mock_get.call_args[0][0]
        assert "sok" in called_url
        assert "geonorge.no" in called_url

    def test_coordinates_url_contains_lat_lon(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp) as mock_get:
            api.search_address(lat=59.9139, lon=10.7522, search_type="coordinates")
        called_url = mock_get.call_args[0][0]
        assert "lat=" in called_url
        assert "lon=" in called_url

    def test_auto_type_uses_address_when_no_coords(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp) as mock_get:
            api.search_address(address="Storgata 1", search_type="auto")
        called_url = mock_get.call_args[0][0]
        assert "sok" in called_url

    def test_auto_type_uses_coordinates_when_provided(self, api, capsys):
        mock_resp = _mock_http_response(200, GEONORGE_ADDRESS_RESPONSE)
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp) as mock_get:
            api.search_address(lat=59.9, lon=10.7, search_type="auto")
        called_url = mock_get.call_args[0][0]
        assert "punktsok" in called_url

    def test_empty_list_response_returns_none(self, api, capsys):
        mock_resp = _mock_http_response(200, [])
        with patch("kartverkets_api.kartverket.requests.get", return_value=mock_resp):
            result = api.search_address(address="Ukjent gate", search_type="address")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# decode_address
# ─────────────────────────────────────────────────────────────────────────────

class TestDecodeAddress:
    def test_valid_address_returns_list_of_dicts(self, api):
        with patch.object(api, "search_address", return_value=GEONORGE_ADDRESS_RESPONSE):
            result = api.decode_address(address="Storgata 1, Oslo")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_valid_coordinates_return_result(self, api):
        with patch.object(api, "search_address", return_value=GEONORGE_ADDRESS_RESPONSE):
            result = api.decode_address(lat=59.9139, lon=10.7522)
        assert result is not None

    def test_no_geonorge_result_falls_back_to_nominatim(self, api):
        nominatim_resp = _mock_http_response(200, NOMINATIM_RESPONSE)
        # Første kall fra search_address (address) returnerer tom respons
        # Andre kall (fra nominatim-koordinater) returnerer gyldig respons
        with patch.object(api, "search_address", side_effect=[
            {"adresser": []},        # geonorge address → ingen treff
            GEONORGE_ADDRESS_RESPONSE  # geonorge coordinates (etter nominatim) → treff
        ]):
            with patch("kartverkets_api.kartverket.requests.get", return_value=nominatim_resp):
                result = api.decode_address(address="Ukjent gate 999")
        assert result is not None

    def test_all_sources_fail_returns_none(self, api):
        failed_resp = _mock_http_response(200, [])  # Nominatim returnerer tom liste
        with patch.object(api, "search_address", return_value={"adresser": []}):
            with patch("kartverkets_api.kartverket.requests.get", return_value=failed_resp):
                result = api.decode_address(address="Totalt ukjent gate")
        assert result is None

    def test_lat_lon_prioritized_over_address(self, api):
        with patch.object(api, "search_address", return_value=GEONORGE_ADDRESS_RESPONSE) as mock_search:
            api.decode_address(lat=59.9139, lon=10.7522, address="Storgata 1")
        # Første kall skal bruke koordinater (search_type="coordinates")
        first_call_kwargs = mock_search.call_args_list[0][1]
        assert "lat" in first_call_kwargs

    def test_search_address_exception_logs_error_and_continues(self, api):
        failed_resp = _mock_http_response(200, [])
        with patch.object(api, "search_address", side_effect=Exception("Nettverksfeil")):
            with patch("kartverkets_api.kartverket.requests.get", return_value=failed_resp):
                result = api.decode_address(address="Storgata 1")
        api.logger.error.assert_called()
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# get_by_property  (async)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetByProperty:
    def _make_result_df(self):
        return pd.DataFrame({
            "kommunenummer": ["0301"],
            "gaardsnummer": [12],
            "bruksnummer": [3],
            "festenummer": [0],
            "seksjonsnummer": [0],
            "omsetning_vederlag_beloepsverdi": [5_000_000],
        })

    @pytest.mark.asyncio
    async def test_returns_dataframe_on_success(self, api):
        expected_df = self._make_result_df()
        api._get_by_property_internal = AsyncMock(return_value=expected_df)
        properties = [{"kommunenummer": "0301", "gaardsnummer": 12, "bruksnummer": 3,
                        "festenummer": 0, "seksjonsnummer": 0}]
        result = await api.get_by_property(properties)
        assert isinstance(result, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_internal_called_with_correct_args(self, api):
        api._get_by_property_internal = AsyncMock(return_value=self._make_result_df())
        properties = [{"kommunenummer": "0301", "gaardsnummer": 12, "bruksnummer": 3,
                        "festenummer": 0, "seksjonsnummer": 0}]
        await api.get_by_property(properties, transfer_type="historical", ownership_type="eier")
        api._get_by_property_internal.assert_called_once_with(
            properties, transfer_type="historical", ownership_type="eier"
        )

    @pytest.mark.asyncio
    async def test_timeout_error_logs_and_returns_none(self, api):
        import asyncio
        api._get_by_property_internal = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await api.get_by_property([], timeout=0.001)
        api.logger.error.assert_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_unexpected_exception_logs_and_returns_none(self, api):
        api._get_by_property_internal = AsyncMock(side_effect=RuntimeError("Uventet feil"))
        result = await api.get_by_property([])
        api.logger.error.assert_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_internal_returns_none_propagated(self, api):
        api._get_by_property_internal = AsyncMock(return_value=None)
        result = await api.get_by_property([])
        assert result is None
