"""
Unit-tester for DataApi.

Tester rene transformasjons- og hjelpemetoder uten nettverkskall:
  - _encode_address
  - transform_single_nomi / transformer_nomi
  - transform_single_geonorge / transformer_geonorge
  - transform_cars
  - commit_batch
  - save_cars
  - save_func
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, call, patch

from sibr_api import NotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES – delte testdata
# ─────────────────────────────────────────────────────────────────────────────

NOMI_RESPONSE = {
    "place_id": 123,
    "lat": "59.9139",
    "lon": "10.7522",
    "display_name": "Oslo sentrum, Oslo, Norge",
    "addresstype": "suburb",
}

GEONORGE_RESPONSE = {
    "adresser": [
        {
            "adresseId": "abc123",
            "adressenavn": "Storgata",
            "husnummer": 1,
            "postnummer": "0155",
            "poststed": "OSLO",
            "kommunenummer": "0301",
            "kommunenavn": "Oslo",
            "representasjonspunkt": {
                "lat": 59.9139,
                "lon": 10.7522,
                "epsg": "EPSG:4258",
            },
        }
    ],
    "metadata": {
        "sokeStreng": "Storgata 1, Oslo",
        "totaltAntallTreff": 1,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# _encode_address
# ─────────────────────────────────────────────────────────────────────────────

class TestEncodeAddress:
    def test_normal_address_returns_encoded_string(self, api):
        result = api._encode_address("Storgata 1, Oslo")
        assert isinstance(result, str)
        assert "Storgata" in result
        assert " " not in result  # spaces skal være URL-kodet

    def test_address_with_slash_strips_apartment_number(self, api):
        # "Kirkeveien 51/B, 0368 Oslo" → "Kirkeveien 51,  0368 Oslo" → encoded
        result = api._encode_address("Kirkeveien 51/B, 0368 Oslo")
        assert result is not None
        assert isinstance(result, str)
        # Leilighetsnummeret (B) skal ikke være med
        assert "B" not in result.replace("%2C", "").replace("+", "")

    def test_address_with_slash_numeric_apartment(self, api):
        result = api._encode_address("Storgata 1/2, 0123 Oslo")
        assert result is not None
        assert isinstance(result, str)

    def test_empty_string_returns_none(self, api):
        result = api._encode_address("")
        assert result is None

    def test_only_whitespace_encoded_to_plus_signs(self, api):
        # quote_plus("   ") == "+++" – pluss-tegn strip()s ikke, returneres som "+++"
        result = api._encode_address("   ")
        assert result == "+++"

    def test_none_address_raises_type_error(self, api):
        with pytest.raises(TypeError):
            api._encode_address(None)

    def test_result_is_url_safe(self, api):
        result = api._encode_address("Karl Johans gate 1, Oslo")
        # Ingen ulovlige tegn i URL (sjekk at det er bare ASCII)
        assert result.isascii()


# ─────────────────────────────────────────────────────────────────────────────
# transform_single_nomi
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformSingleNomi:
    def test_tuple_input_returns_dataframe_with_correct_columns(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        required = {"item_id", "lat", "lng", "status", "geocoder", "adressetekst", "get_date"}
        assert required.issubset(set(df.columns))

    def test_tuple_input_sets_item_id(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert df["item_id"].iloc[0] == "id_001"

    def test_tuple_input_status_is_ok(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert df["status"].iloc[0] == "OK"

    def test_tuple_input_geocoder_is_nominatim(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert df["geocoder"].iloc[0] == "nominatim"

    def test_lat_lng_converted_to_float(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert pd.api.types.is_float_dtype(df["lat"])
        assert pd.api.types.is_float_dtype(df["lng"])
        assert abs(df["lat"].iloc[0] - 59.9139) < 0.0001
        assert abs(df["lng"].iloc[0] - 10.7522) < 0.0001

    def test_lon_renamed_to_lng(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert "lng" in df.columns
        assert "lon" not in df.columns

    def test_display_name_renamed_to_adressetekst(self, api):
        df = api.transform_single_nomi(("id_001", NOMI_RESPONSE))
        assert "adressetekst" in df.columns
        assert df["adressetekst"].iloc[0] == "Oslo sentrum, Oslo, Norge"

    def test_dict_input_item_id_is_none(self, api):
        df = api.transform_single_nomi(NOMI_RESPONSE)
        assert df["item_id"].iloc[0] is None

    def test_none_data_with_item_id_returns_no_results_df(self, api):
        df = api.transform_single_nomi(("id_002", None))
        assert df["status"].iloc[0] == "NO_RESULTS"
        assert df["item_id"].iloc[0] == "id_002"
        assert df["geocoder"].iloc[0] == "nominatim"

    def test_wrong_type_raises_type_error(self, api):
        with pytest.raises(TypeError):
            api.transform_single_nomi(["not", "a", "tuple"])

    def test_missing_optional_cols_are_added_as_none(self, api):
        # Response med lat/lon men uten display_name → adressetekst legges til som None
        response_no_display_name = {"place_id": 99, "lat": "59.9", "lon": "10.7"}
        df = api.transform_single_nomi(("id_003", response_no_display_name))
        assert "adressetekst" in df.columns
        assert df["adressetekst"].iloc[0] is None


# ─────────────────────────────────────────────────────────────────────────────
# transformer_nomi
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformerNomi:
    def test_returns_combined_dataframe(self, api):
        results = [
            ("id_001", NOMI_RESPONSE),
            ("id_002", NOMI_RESPONSE),
        ]
        df = api.transformer_nomi(results)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_none_items_are_filtered_out(self, api):
        results = [("id_001", NOMI_RESPONSE), None, ("id_002", NOMI_RESPONSE)]
        df = api.transformer_nomi(results)
        assert len(df) == 2

    def test_empty_list_returns_none(self, api):
        result = api.transformer_nomi([])
        assert result is None

    def test_none_input_returns_none(self, api):
        result = api.transformer_nomi(None)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# transform_single_geonorge
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformSingleGeonorge:
    def test_tuple_input_returns_dataframe(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_tuple_input_sets_item_id(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert df["item_id"].iloc[0] == "id_001"

    def test_status_is_ok(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert df["status"].iloc[0] == "OK"

    def test_geocoder_is_geonorge(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert df["geocoder"].iloc[0] == "geonorge"

    def test_lon_renamed_to_lng(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert "lng" in df.columns
        assert "lon" not in df.columns

    def test_dict_input_item_id_is_none(self, api):
        df = api.transform_single_geonorge(GEONORGE_RESPONSE)
        assert df["item_id"].iloc[0] is None

    def test_none_data_with_item_id_returns_no_results_df(self, api):
        df = api.transform_single_geonorge(("id_002", None))
        assert df["status"].iloc[0] == "NO_RESULTS"
        assert df["item_id"].iloc[0] == "id_002"
        assert df["geocoder"].iloc[0] == "geonorge"

    def test_empty_adresser_returns_no_results_df_with_id(self, api):
        empty_response = {
            "adresser": [],
            "metadata": {"sokeStreng": "Ukjent gate", "totaltAntallTreff": 0},
        }
        df = api.transform_single_geonorge(("id_003", empty_response))
        assert df is not None
        assert df["status"].iloc[0] == "NO_RESULTS"

    def test_wrong_type_raises_type_error(self, api):
        with pytest.raises(TypeError):
            api.transform_single_geonorge(["not", "valid"])

    def test_representasjonspunkt_fields_merged(self, api):
        df = api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        # lat og lng fra representasjonspunkt skal ligge i DF
        assert "lat" in df.columns

    def test_ok_responses_incremented_on_success(self, api):
        api.ok_responses = 0
        api.transform_single_geonorge(("id_001", GEONORGE_RESPONSE))
        assert api.ok_responses == 1

    def test_fail_responses_incremented_on_empty(self, api):
        api.fail_responses = 0
        empty_response = {"adresser": [], "metadata": {}}
        api.transform_single_geonorge(("id_003", empty_response))
        assert api.fail_responses == 1


# ─────────────────────────────────────────────────────────────────────────────
# transformer_geonorge
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformerGeonorge:
    def test_returns_combined_dataframe(self, api):
        results = [
            ("id_001", GEONORGE_RESPONSE),
            ("id_002", GEONORGE_RESPONSE),
        ]
        df = api.transformer_geonorge(results)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_none_items_are_filtered_out(self, api):
        results = [("id_001", GEONORGE_RESPONSE), None, ("id_002", GEONORGE_RESPONSE)]
        df = api.transformer_geonorge(results)
        assert len(df) == 2

    def test_empty_list_returns_none(self, api):
        result = api.transformer_geonorge([])
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# transform_cars (passthrough)
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformCars:
    def test_returns_input_unchanged(self, api):
        responses = [("id_001", {"data": "x"}), ("id_002", None)]
        result = api.transform_cars(responses)
        assert result is responses

    def test_empty_list_returned_as_is(self, api):
        result = api.transform_cars([])
        assert result == []

    def test_none_returned_as_is(self, api):
        result = api.transform_cars(None)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# commit_batch
# ─────────────────────────────────────────────────────────────────────────────

class TestCommitBatch:
    def test_successful_commit_returns_true(self, api):
        batch = MagicMock()
        batch.commit.return_value = None
        assert api.commit_batch(batch) is True

    def test_failed_commit_returns_false(self, api):
        batch = MagicMock()
        batch.commit.side_effect = Exception("Firestore nede")
        assert api.commit_batch(batch) is False

    def test_commit_is_called_once(self, api):
        batch = MagicMock()
        api.commit_batch(batch)
        batch.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# save_cars
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveCars:
    def _make_responses(self, n):
        return [(f"id_{i}", {"reg_num": f"AB{i}1234"}) for i in range(n)]

    def test_single_batch_committed(self, api):
        api.db = MagicMock()
        mock_batch = MagicMock()
        api.db.batch.return_value = mock_batch

        responses = self._make_responses(3)
        with patch.object(api, "commit_batch", return_value=True) as mock_commit:
            api.save_cars(responses, batch_size=200)
            assert mock_commit.call_count == 1

    def test_multiple_batches_on_large_input(self, api):
        api.db = MagicMock()
        api.db.batch.return_value = MagicMock()

        responses = self._make_responses(250)
        with patch.object(api, "commit_batch", return_value=True) as mock_commit:
            api.save_cars(responses, batch_size=100)
            # 250 items / 100 per batch → 3 batches (100 + 100 + 50)
            assert mock_commit.call_count == 3

    def test_each_item_set_in_firestore(self, api):
        api.db = MagicMock()
        mock_batch = MagicMock()
        api.db.batch.return_value = mock_batch
        api.db.collection.return_value.document.return_value = MagicMock()

        responses = self._make_responses(2)
        with patch.object(api, "commit_batch", return_value=True):
            api.save_cars(responses, batch_size=200)

        assert mock_batch.set.call_count == 2

    def test_empty_responses_no_commit(self, api):
        api.db = MagicMock()
        api.db.batch.return_value = MagicMock()

        with patch.object(api, "commit_batch", return_value=True) as mock_commit:
            api.save_cars([], batch_size=200)
            # Tom liste: én tom batch legges til og commites
            assert mock_commit.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# save_func
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveFunc:
    def _make_df(self):
        return pd.DataFrame({"item_id": ["id_001"], "lat": [59.9], "lng": [10.7]})

    def test_default_table_and_dataset(self, api):
        api.bq = MagicMock()
        df = self._make_df()
        api.save_func(df)
        api.bq.to_bq.assert_called_once()
        _, kwargs = api.bq.to_bq.call_args
        assert kwargs["table_name"] == "coordinates"
        assert kwargs["dataset_name"] == "staging"

    def test_custom_table_and_dataset(self, api):
        api.bq = MagicMock()
        df = self._make_df()
        api.save_func(df, table_name="my_table", dataset_name="my_dataset")
        _, kwargs = api.bq.to_bq.call_args
        assert kwargs["table_name"] == "my_table"
        assert kwargs["dataset_name"] == "my_dataset"

    def test_merge_on_item_id(self, api):
        api.bq = MagicMock()
        df = self._make_df()
        api.save_func(df)
        _, kwargs = api.bq.to_bq.call_args
        assert kwargs["merge_on"] == ["item_id"]
        assert kwargs["if_exists"] == "merge"
