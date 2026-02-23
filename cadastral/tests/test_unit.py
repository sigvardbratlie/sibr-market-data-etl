"""
Unit-tester for kartverketsAPI.

Tester rene transformasjons- og hjelpemetoder uten nettverkskall:
  - _ensure_col_names
  - transform_coop
  - transform_cadastrals
  - _encode_address
  - transform_single_geonorge
  - _object_to_dataframe
  - trim_output
"""
import pandas as pd
import pytest
from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Delte testdata
# ─────────────────────────────────────────────────────────────────────────────

GEONORGE_RESPONSE = {
    "adresser": [
        {
            "adressetekst": "Storgata 1",
            "postnummer": "0155",
            "poststed": "OSLO",
            "kommunenummer": "0301",
            "gardsnummer": 12,
            "bruksnummer": 3,
            "festenummer": 0,
            "meterdistansetilpunkt": 5.2,
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

REQUEST_COLS_EIER = [
    "kommunenummer", "gaardsnummer", "bruksnummer", "festenummer", "seksjonsnummer"
]
REQUEST_COLS_ANDEL = ["borettslagnummer", "andelsnummer"]


# ─────────────────────────────────────────────────────────────────────────────
# _ensure_col_names
# ─────────────────────────────────────────────────────────────────────────────

class TestEnsureColNames:
    def test_lowercase_conversion(self, api):
        assert api._ensure_col_names(["Kommunenummer"]) == ["kommunenummer"]

    def test_spaces_to_underscores(self, api):
        assert api._ensure_col_names(["gards nummer"]) == ["gards_nummer"]

    def test_hyphens_to_underscores(self, api):
        assert api._ensure_col_names(["gjerde-nummer"]) == ["gjerde_nummer"]

    def test_dots_to_underscores(self, api):
        assert api._ensure_col_names(["id.value"]) == ["id_value"]

    def test_norwegian_o_replaced(self, api):
        assert api._ensure_col_names(["brønn"]) == ["bronn"]

    def test_norwegian_a_replaced(self, api):
        assert api._ensure_col_names(["æble"]) == ["able"]

    def test_norwegian_aa_replaced(self, api):
        # å → a (én-til-én erstatning, ikke "aa")
        assert api._ensure_col_names(["gårds"]) == ["gards"]

    def test_combined_transformations(self, api):
        # å→a, space→_, hyphen→_, lower
        assert api._ensure_col_names(["Gårds Nummer-2"]) == ["gards_nummer_2"]

    def test_leading_trailing_spaces_stripped(self, api):
        assert api._ensure_col_names(["  kommunenummer  "]) == ["kommunenummer"]

    def test_empty_list(self, api):
        assert api._ensure_col_names([]) == []

    def test_multiple_columns(self, api):
        result = api._ensure_col_names(["Kommunenummer", "GaardsNummer", "Bruksnummer"])
        assert result == ["kommunenummer", "gaardsnummer", "bruksnummer"]


# ─────────────────────────────────────────────────────────────────────────────
# transform_coop
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformCoop:
    def _make_df(self, include_item_id=True):
        data = {
            "coop_org_num": [12345, 12345, 99999],
            "coop_unit_num": [1, 2, 1],
        }
        if include_item_id:
            data["item_id"] = ["id1", "id2", "id3"]
        return pd.DataFrame(data)

    def test_renames_columns_correctly(self, api):
        df = self._make_df()
        result = api.transform_coop(df)
        assert "borettslagnummer" in result.columns
        assert "andelsnummer" in result.columns
        assert "coop_org_num" not in result.columns
        assert "coop_unit_num" not in result.columns

    def test_item_id_set_as_index(self, api):
        df = self._make_df()
        result = api.transform_coop(df)
        assert result.index.name == "item_id"

    def test_values_converted_to_int(self, api):
        df = self._make_df()
        result = api.transform_coop(df)
        assert result["borettslagnummer"].dtype in (int, "int64", "int32")
        assert result["andelsnummer"].dtype in (int, "int64", "int32")

    def test_nan_rows_dropped(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "coop_org_num": [12345, None],
            "coop_unit_num": [1, 2],
        })
        result = api.transform_coop(df)
        assert len(result) == 1
        assert result.index[0] == "id1"

    def test_duplicate_rows_deduplicated(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "coop_org_num": [12345, 12345],
            "coop_unit_num": [1, 1],  # same combination
        })
        result = api.transform_coop(df)
        assert len(result) == 1

    def test_missing_item_id_logs_warning(self, api):
        df = self._make_df(include_item_id=False)
        api.transform_coop(df)
        api.logger.warning.assert_called()

    def test_missing_required_col_raises_error(self, api):
        # coop_unit_num mangler → etter rename er andelsnummer fraværende
        # dropna(subset=["andelsnummer"]) gir KeyError
        df = pd.DataFrame({
            "item_id": ["id1"],
            "coop_org_num": [12345],
        })
        with pytest.raises((ValueError, KeyError)):
            api.transform_coop(df, request_cols=["borettslagnummer", "andelsnummer"])

    def test_non_numeric_values_coerced_to_nan_and_dropped(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "coop_org_num": [12345, "ikke_et_tall"],
            "coop_unit_num": [1, 2],
        })
        result = api.transform_coop(df)
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# transform_cadastrals
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformCadastrals:
    def _make_df(self, **overrides):
        data = {
            "item_id": ["id1"],
            "municipality_num": [301],
            "cadastral_num": [12],
            "unit_num": [3],
            "leasehold_num": [0],
            "section_num": [0],
        }
        data.update(overrides)
        return pd.DataFrame(data)

    def test_renames_columns_correctly(self, api):
        result = api.transform_cadastrals(self._make_df())
        assert "kommunenummer" in result.columns
        assert "gaardsnummer" in result.columns
        assert "bruksnummer" in result.columns
        assert "festenummer" in result.columns
        assert "seksjonsnummer" in result.columns

    def test_kommunenummer_zero_padded_to_4_digits(self, api):
        result = api.transform_cadastrals(self._make_df(municipality_num=[301]))
        assert result["kommunenummer"].iloc[0] == "0301"

    def test_kommunenummer_4_digit_stays_unchanged(self, api):
        result = api.transform_cadastrals(self._make_df(municipality_num=[3014]))
        assert result["kommunenummer"].iloc[0] == "3014"

    def test_item_id_set_as_index(self, api):
        result = api.transform_cadastrals(self._make_df())
        assert result.index.name == "item_id"

    def test_row_with_gaardsnummer_zero_is_filtered(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "municipality_num": [301, 301],
            "cadastral_num": [0, 12],   # id1 har gaardsnummer=0 → skal filtreres
            "unit_num": [3, 3],
            "leasehold_num": [0, 0],
            "section_num": [0, 0],
        })
        result = api.transform_cadastrals(df)
        assert len(result) == 1
        assert result.index[0] == "id2"

    def test_row_with_null_gaardsnummer_is_dropped(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "municipality_num": [301, 301],
            "cadastral_num": [None, 12],
            "unit_num": [3, 3],
            "leasehold_num": [0, 0],
            "section_num": [0, 0],
        })
        result = api.transform_cadastrals(df)
        assert len(result) == 1

    def test_missing_festenummer_filled_with_zero(self, api):
        df = pd.DataFrame({
            "item_id": ["id1"],
            "municipality_num": [301],
            "cadastral_num": [12],
            "unit_num": [3],
            # leasehold_num og section_num mangler
        })
        result = api.transform_cadastrals(df)
        assert result["festenummer"].iloc[0] == 0
        assert result["seksjonsnummer"].iloc[0] == 0

    def test_duplicate_properties_deduplicated(self, api):
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "municipality_num": [301, 301],
            "cadastral_num": [12, 12],
            "unit_num": [3, 3],
            "leasehold_num": [0, 0],
            "section_num": [0, 0],
        })
        result = api.transform_cadastrals(df)
        assert len(result) == 1

    def test_missing_required_column_raises_error(self, api):
        # cadastral_num mangler → etter rename er gaardsnummer fraværende
        # dropna(subset=["gaardsnummer"]) gir KeyError
        df = pd.DataFrame({
            "item_id": ["id1"],
            "municipality_num": [301],
            "unit_num": [3],
        })
        with pytest.raises((ValueError, KeyError)):
            api.transform_cadastrals(df)

    def test_kommunenummer_zero_row_filtered_out(self, api):
        # municipality_num=0 → kommunenummer="0000" → skal filtreres
        df = pd.DataFrame({
            "item_id": ["id1", "id2"],
            "municipality_num": [0, 301],
            "cadastral_num": [12, 12],
            "unit_num": [3, 3],
            "leasehold_num": [0, 0],
            "section_num": [0, 0],
        })
        result = api.transform_cadastrals(df)
        assert len(result) == 1
        assert result.index[0] == "id2"


# ─────────────────────────────────────────────────────────────────────────────
# _encode_address
# ─────────────────────────────────────────────────────────────────────────────

class TestEncodeAddress:
    def test_normal_address_returns_encoded_string(self, api):
        result = api._encode_address("Storgata 1, Oslo")
        assert isinstance(result, str)
        assert " " not in result

    def test_result_is_url_safe(self, api):
        result = api._encode_address("Karl Johans gate 1, Oslo")
        assert result.isascii()

    def test_empty_string_returns_none(self, api):
        result = api._encode_address("")
        assert result is None

    def test_address_with_slash_strips_apartment(self, api):
        # "Kirkeveien 51/B, 0368 Oslo" → apartment (B) fjernes
        result = api._encode_address("Kirkeveien 51/B, 0368 Oslo")
        assert result is not None
        # "B" skal ikke vises etter dekoding (men kan dukke opp som %2C etc.)
        decoded = result.replace("+", " ").replace("%2C", ",")
        assert "B" not in decoded

    def test_address_with_numeric_slash_encoded(self, api):
        result = api._encode_address("Storgata 1/2, 0123 Oslo")
        assert result is not None
        assert isinstance(result, str)

    def test_none_raises_type_error(self, api):
        with pytest.raises((TypeError, AttributeError)):
            api._encode_address(None)


# ─────────────────────────────────────────────────────────────────────────────
# transform_single_geonorge  (kartverketsAPI-versjon – returnerer list[dict])
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformSingleGeonorge:
    def test_returns_list_of_dicts(self, api):
        result = api.transform_single_geonorge(GEONORGE_RESPONSE)
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_gardsnummer_renamed_to_gaardsnummer(self, api):
        result = api.transform_single_geonorge(GEONORGE_RESPONSE)
        assert "gaardsnummer" in result[0]
        assert "gardsnummer" not in result[0]

    def test_expected_columns_present(self, api):
        result = api.transform_single_geonorge(GEONORGE_RESPONSE)
        expected = {"kommunenummer", "gaardsnummer", "bruksnummer", "lat", "lon"}
        assert expected.issubset(result[0].keys())

    def test_lat_lon_values_correct(self, api):
        result = api.transform_single_geonorge(GEONORGE_RESPONSE)
        assert abs(result[0]["lat"] - 59.9139) < 0.001
        assert abs(result[0]["lon"] - 10.7522) < 0.001

    def test_empty_adresser_returns_none(self, api):
        empty_response = {
            "adresser": [],
            "metadata": {"sokeStreng": "Ukjent gate", "totaltAntallTreff": 0},
        }
        result = api.transform_single_geonorge(empty_response)
        assert result is None

    def test_none_response_raises_type_error(self, api):
        # None er ikke en dict, koden kaster TypeError
        with pytest.raises(TypeError):
            api.transform_single_geonorge(None)

    def test_non_dict_raises_type_error(self, api):
        with pytest.raises(TypeError):
            api.transform_single_geonorge(["not", "a", "dict"])

    def test_extra_columns_dropped(self, api):
        result = api.transform_single_geonorge(GEONORGE_RESPONSE)
        allowed = {
            "kommunenummer", "gaardsnummer", "bruksnummer", "festenummer",
            "adressetekst", "postnummer", "poststed", "meterdistansetilpunkt",
            "lat", "lon",
        }
        assert set(result[0].keys()).issubset(allowed)


# ─────────────────────────────────────────────────────────────────────────────
# _object_to_dataframe
# ─────────────────────────────────────────────────────────────────────────────

class TestObjectToDataframe:
    def _make_objects(self, n=2):
        return [
            {"id": {"value": f"trans_{i:03d}"}, "someField": f"data_{i}"}
            for i in range(n)
        ]

    def test_returns_dataframe(self, api):
        result = api._object_to_dataframe(self._make_objects())
        assert isinstance(result, pd.DataFrame)

    def test_row_count_matches_input(self, api):
        result = api._object_to_dataframe(self._make_objects(3))
        assert len(result) == 3

    def test_column_names_normalized(self, api):
        result = api._object_to_dataframe(self._make_objects())
        # "id.value" flates ut med json_normalize og normaliseres til "id_value"
        assert "id_value" in result.columns

    def test_property_map_creates_property_id_column(self, api):
        objects = [{"id": {"value": "trans_001"}, "data": "x"}]
        property_map = {
            "prop_001": {"overdragelse_ids": ["trans_001"], "andel_ids": []}
        }
        result = api._object_to_dataframe(objects, property_map=property_map)
        assert "property_id" in result.columns
        assert result["property_id"].iloc[0] == "prop_001"

    def test_no_property_map_no_property_id_column(self, api):
        result = api._object_to_dataframe(self._make_objects())
        assert "property_id" not in result.columns


# ─────────────────────────────────────────────────────────────────────────────
# trim_output
# ─────────────────────────────────────────────────────────────────────────────

class TestTrimOutput:
    def _make_df_and_db(self):
        df = pd.DataFrame({
            "kommunenummer": ["0301"],
            "gaardsnummer": [12],
            "bruksnummer": [3],
            "festenummer": [0],
            "seksjonsnummer": [0],
            "id_value": ["trans_001"],
            "omsetning_vederlag_beloepsverdi": [5_000_000],
        })
        db = pd.DataFrame(
            {
                "kommunenummer": ["0301"],
                "gaardsnummer": [12],
                "bruksnummer": [3],
                "festenummer": [0],
                "seksjonsnummer": [0],
            },
            index=pd.Index(["id_001"], name="item_id"),
        )
        return df, db

    def test_active_true_for_active_transfer_type(self, api):
        df, db = self._make_df_and_db()
        result = api.trim_output(df, db, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        assert result["active"].iloc[0] == True  # noqa: E712 – numpy bool trenger ==

    def test_active_false_for_historical_transfer_type(self, api):
        df, db = self._make_df_and_db()
        result = api.trim_output(df, db, transfer_type="historical", request_cols=REQUEST_COLS_EIER)
        assert result["active"].iloc[0] == False  # noqa: E712

    def test_get_date_column_added(self, api):
        df, db = self._make_df_and_db()
        result = api.trim_output(df, db, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        assert "get_date" in result.columns

    def test_request_cols_removed_from_output(self, api):
        df, db = self._make_df_and_db()
        result = api.trim_output(df, db, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        for col in REQUEST_COLS_EIER:
            assert col not in result.columns

    def test_item_id_from_db_merged_in(self, api):
        df, db = self._make_df_and_db()
        result = api.trim_output(df, db, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        assert "item_id" in result.columns
        assert result["item_id"].iloc[0] == "id_001"

    def test_known_drop_columns_removed_silently(self, api):
        df, db = self._make_df_and_db()
        # Legg til en kjent kolonne som skal droppes
        df["omsetning_oppdateringsdato_timestamp"] = [None]
        result = api.trim_output(df, db, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        assert "omsetning_oppdateringsdato_timestamp" not in result.columns

    def test_dtype_mismatch_logs_warning(self, api):
        df, db = self._make_df_and_db()
        # Tving int-dtype i df for gaardsnummer (allerede int), men string i db
        db_str = db.copy()
        db_str["gaardsnummer"] = db_str["gaardsnummer"].astype(str)
        api.trim_output(df, db_str, transfer_type="active", request_cols=REQUEST_COLS_EIER)
        api.logger.warning.assert_called()
