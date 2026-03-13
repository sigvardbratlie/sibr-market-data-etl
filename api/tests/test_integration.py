"""
Integrasjonstester for DataApi – async metoder med mocka HTTP.

Tester at get_nomi, get_geonorge og get_car håndterer alle responssenarier korrekt
uten å gjøre ekte nettverkskall. fetch_single mockes med AsyncMock.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from api import NotFoundError

# ─────────────────────────────────────────────────────────────────────────────
# Delte testdata
# ─────────────────────────────────────────────────────────────────────────────

NOMI_DICT = {
    "place_id": 42,
    "lat": "59.9139",
    "lon": "10.7522",
    "display_name": "Oslo, Norge",
    "addresstype": "city",
}

GEONORGE_DICT = {
    "adresser": [
        {
            "adresseId": "abc",
            "adressenavn": "Storgata",
            "husnummer": 1,
            "postnummer": "0155",
            "poststed": "OSLO",
            "kommunenummer": "0301",
            "kommunenavn": "Oslo",
            "representasjonspunkt": {"lat": 59.9139, "lon": 10.7522, "epsg": "EPSG:4258"},
        }
    ],
    "metadata": {"sokeStreng": "Storgata 1", "totaltAntallTreff": 1},
}

CAR_DICT = {"kjoretoydataListe": [{"kjoretoyId": {"kjennemerke": "AB12345"}}]}


# ─────────────────────────────────────────────────────────────────────────────
# get_nomi
# ─────────────────────────────────────────────────────────────────────────────

class TestGetNomi:
    @pytest.mark.asyncio
    async def test_fetch_returns_dict(self, api):
        api.fetch_single = AsyncMock(return_value=NOMI_DICT)
        result = await api.get_nomi("Storgata 1, Oslo")
        assert result == NOMI_DICT

    @pytest.mark.asyncio
    async def test_fetch_returns_list_with_one_item(self, api):
        api.fetch_single = AsyncMock(return_value=[NOMI_DICT])
        result = await api.get_nomi("Storgata 1, Oslo")
        assert result == NOMI_DICT

    @pytest.mark.asyncio
    async def test_fetch_returns_list_with_multiple_items(self, api):
        two_items = [NOMI_DICT, NOMI_DICT]
        api.fetch_single = AsyncMock(return_value=two_items)
        result = await api.get_nomi("Storgata 1, Oslo")
        assert result == two_items

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_list(self, api):
        api.fetch_single = AsyncMock(return_value=[])
        result = await api.get_nomi("Ukjent gate 999")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none(self, api):
        api.fetch_single = AsyncMock(return_value=None)
        result = await api.get_nomi("Ukjent gate 999")
        assert result is None

    @pytest.mark.asyncio
    async def test_not_found_error_returns_none(self, api):
        api.fetch_single = AsyncMock(side_effect=NotFoundError("404"))
        result = await api.get_nomi("Finnes ikke gate 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_fail_counter_incremented_on_empty(self, api):
        api.fetch_single = AsyncMock(return_value=[])
        api.fail_responses = 0
        await api.get_nomi("Ukjent gate")
        assert api.fail_responses == 1

    @pytest.mark.asyncio
    async def test_ok_counter_incremented_on_success(self, api):
        api.fetch_single = AsyncMock(return_value=NOMI_DICT)
        api.ok_responses = 0
        await api.get_nomi("Storgata 1")
        assert api.ok_responses == 1

    @pytest.mark.asyncio
    async def test_invalid_address_with_slash_still_calls_fetch(self, api):
        api.fetch_single = AsyncMock(return_value=NOMI_DICT)
        await api.get_nomi("Kirkeveien 51/B, 0368 Oslo")
        api.fetch_single.assert_called_once()

    @pytest.mark.asyncio
    async def test_encoded_address_used_in_url(self, api):
        api.fetch_single = AsyncMock(return_value=NOMI_DICT)
        await api.get_nomi("Karl Johans gate 1")
        called_url = api.fetch_single.call_args[0][0]
        # URL-enkoding erstatter mellomrom med +
        assert "Karl+Johans" in called_url or "Karl%20Johans" in called_url


# ─────────────────────────────────────────────────────────────────────────────
# get_geonorge
# ─────────────────────────────────────────────────────────────────────────────

class TestGetGeonorge:
    @pytest.mark.asyncio
    async def test_fetch_returns_dict(self, api):
        api.fetch_single = AsyncMock(return_value=GEONORGE_DICT)
        result = await api.get_geonorge("Storgata 1, Oslo")
        assert result == GEONORGE_DICT

    @pytest.mark.asyncio
    async def test_fetch_returns_list_with_one_item(self, api):
        api.fetch_single = AsyncMock(return_value=[GEONORGE_DICT])
        result = await api.get_geonorge("Storgata 1, Oslo")
        assert result == GEONORGE_DICT

    @pytest.mark.asyncio
    async def test_fetch_returns_list_with_multiple_items(self, api):
        two_items = [GEONORGE_DICT, GEONORGE_DICT]
        api.fetch_single = AsyncMock(return_value=two_items)
        result = await api.get_geonorge("Storgata 1, Oslo")
        assert result == two_items

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_list(self, api):
        api.fetch_single = AsyncMock(return_value=[])
        result = await api.get_geonorge("Ukjent gate 999")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none(self, api):
        api.fetch_single = AsyncMock(return_value=None)
        result = await api.get_geonorge("Ukjent gate 999")
        assert result is None

    @pytest.mark.asyncio
    async def test_not_found_error_returns_none(self, api):
        api.fetch_single = AsyncMock(side_effect=NotFoundError("404"))
        result = await api.get_geonorge("Finnes ikke gate 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_geonorge_url_contains_sok_endpoint(self, api):
        api.fetch_single = AsyncMock(return_value=GEONORGE_DICT)
        await api.get_geonorge("Storgata 1")
        called_url = api.fetch_single.call_args[0][0]
        assert "geonorge.no" in called_url
        assert "sok" in called_url

    @pytest.mark.asyncio
    async def test_address_encoded_in_url(self, api):
        api.fetch_single = AsyncMock(return_value=GEONORGE_DICT)
        await api.get_geonorge("Karl Johans gate 1")
        called_url = api.fetch_single.call_args[0][0]
        # Mellomrom skal være URL-enkodert
        assert " " not in called_url


# ─────────────────────────────────────────────────────────────────────────────
# get_car
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCar:
    @pytest.mark.asyncio
    async def test_fetch_returns_valid_response(self, api):
        api.fetch_single = AsyncMock(return_value=CAR_DICT)
        result = await api.get_car("AB12345")
        assert result == CAR_DICT

    @pytest.mark.asyncio
    async def test_fetch_returns_none(self, api):
        api.fetch_single = AsyncMock(return_value=None)
        result = await api.get_car("AB12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_dict(self, api):
        api.fetch_single = AsyncMock(return_value={})
        result = await api.get_car("AB12345")
        # Tom dict er falsy
        assert result is None

    @pytest.mark.asyncio
    async def test_not_found_error_returns_none(self, api):
        api.fetch_single = AsyncMock(side_effect=NotFoundError("404"))
        result = await api.get_car("FINNESIKKE")
        assert result is None

    @pytest.mark.asyncio
    async def test_ok_counter_incremented_on_success(self, api):
        api.fetch_single = AsyncMock(return_value=CAR_DICT)
        api.ok_responses = 0
        await api.get_car("AB12345")
        assert api.ok_responses == 1

    @pytest.mark.asyncio
    async def test_fail_counter_incremented_on_none(self, api):
        api.fetch_single = AsyncMock(return_value=None)
        api.fail_responses = 0
        await api.get_car("AB12345")
        assert api.fail_responses == 1

    @pytest.mark.asyncio
    async def test_fail_counter_incremented_on_not_found(self, api):
        api.fetch_single = AsyncMock(side_effect=NotFoundError())
        api.fail_responses = 0
        await api.get_car("UKJENT")
        assert api.fail_responses == 1

    @pytest.mark.asyncio
    async def test_vegvesen_url_contains_kjennemerke(self, api):
        api.fetch_single = AsyncMock(return_value=CAR_DICT)
        await api.get_car("AB12345")
        called_url = api.fetch_single.call_args[0][0]
        assert "AB12345" in called_url
        assert "vegvesen.no" in called_url

    @pytest.mark.asyncio
    async def test_svv_authorization_header_set(self, api):
        api.fetch_single = AsyncMock(return_value=CAR_DICT)
        api.sv_api_key = "test_key_xyz"
        await api.get_car("AB12345")
        _, kwargs = api.fetch_single.call_args
        headers = kwargs.get("headers", {})
        assert "SVV-Authorization" in headers
        assert "test_key_xyz" in headers["SVV-Authorization"]
