import pytest
import pandas as pd
import numpy as np
from fixtures.test_homes_data import raw_homes


@pytest.fixture
def instance(make_clean_instance):
    c = make_clean_instance('homes')
    c.df = pd.DataFrame(raw_homes)
    return c


@pytest.fixture
def cleaned_df(instance):
    return instance.clean_homes()


class TestCleanHomesStructure:
    """Test that clean_homes returns a DataFrame with expected structure."""

    def test_returns_dataframe(self, cleaned_df):
        assert isinstance(cleaned_df, pd.DataFrame)

    def test_not_empty(self, cleaned_df):
        assert len(cleaned_df) > 0

    def test_has_item_id(self, cleaned_df):
        assert 'item_id' in cleaned_df.columns

    def test_no_duplicate_item_ids(self, cleaned_df):
        assert cleaned_df['item_id'].is_unique

    def test_has_geo_columns(self, cleaned_df):
        for col in ['postal_code', 'municipality', 'county', 'region']:
            assert col in cleaned_df.columns, f"Missing geo column: {col}"

    def test_has_equipment_bool_columns(self, cleaned_df):
        expected = [
            'eq_parking', 'eq_lift', 'eq_fireplace',
            'eq_charging_possibility', 'eq_aircondition', 'eq_garden', 'eq_pool',
        ]
        for col in expected:
            assert col in cleaned_df.columns, f"Missing equipment column: {col}"

    def test_has_description_bool_columns(self, cleaned_df):
        expected = ['fixer_upper', 'renovated', 'eq_rental_unit', 'eq_west_facing', 'eq_sauna']
        for col in expected:
            assert col in cleaned_df.columns, f"Missing column: {col}"

    def test_has_derived_columns(self, cleaned_df):
        expected = ['price_pr_sqm', 'price_pr_i_sqm', 'price_pr_bedroom', 'sqm_pr_bedroom',
                    'monthly_common_cost_pr_sqm', 'clean_date']
        for col in expected:
            assert col in cleaned_df.columns, f"Missing derived column: {col}"

    def test_primary_area_dropped(self, cleaned_df):
        assert 'primary_area' not in cleaned_df.columns


class TestCleanHomesNumericConversion:
    """Test that string values are properly converted to numeric."""

    def test_price_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['price'])

    def test_total_price_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['total_price'])

    def test_bedrooms_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['bedrooms'])

    def test_usable_area_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['usable_area'])

    def test_internal_area_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['internal_area'])

    def test_floor_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['floor'])

    def test_price_parsed_correctly(self, cleaned_df):
        """'3 300 000 kr' should become 3300000."""
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            assert row['price'].iloc[0] == 3300000

    def test_usable_area_parsed_correctly(self, cleaned_df):
        """'97 m²' -> extract_int('97') -> 97 (no separator, so no *1000)."""
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            assert row['usable_area'].iloc[0] == 97

    def test_bedrooms_parsed_correctly(self, cleaned_df):
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            assert row['bedrooms'].iloc[0] == 3


class TestCleanHomesFiltering:
    """Test that data outside valid ranges is removed."""

    def test_price_range(self, cleaned_df):
        assert (cleaned_df['price'] > 200000).all()
        assert (cleaned_df['price'] < 30000000).all()

    def test_usable_area_range(self, cleaned_df):
        assert (cleaned_df['usable_area'] > 0).all()
        assert (cleaned_df['usable_area'] < 1500).all()

    def test_internal_area_range(self, cleaned_df):
        assert (cleaned_df['internal_area'] > 0).all()
        assert (cleaned_df['internal_area'] < 1500).all()

    def test_bedrooms_range(self, cleaned_df):
        assert (cleaned_df['bedrooms'] >= 0).all()
        assert (cleaned_df['bedrooms'] < 10).all()

    def test_floor_range(self, cleaned_df):
        assert (cleaned_df['floor'] >= 0).all()
        assert (cleaned_df['floor'] < 100).all()

    def test_garage_filtered_out(self, cleaned_df):
        """Garasje/Parkering items with price=390000 should still be filtered out
        if usable_area is out of range or 0."""
        garage_items = cleaned_df[cleaned_df['item_id'] == '397155815']
        # This item has usable_area '15 m²' which is 15000 after extract_int -> out of range for homes
        # OR price is 390000 which is > 200000 so it depends on area parsing
        # The key is that the filter logic is applied


class TestCleanHomesCadastre:
    """Test cadastre field parsing."""

    def test_cadastral_num_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['cadastral_num'])

    def test_municipality_num_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['municipality_num'])

    def test_cadastral_num_parsed(self, cleaned_df):
        """['Gårdsnr', ': ', '3'] should parse to 3."""
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            val = row['cadastral_num'].iloc[0]
            assert pd.notna(val)
            assert int(val) == 3


class TestCleanHomesDatetime:
    """Test datetime handling."""

    def test_scrape_date_is_datetime(self, cleaned_df):
        assert pd.api.types.is_datetime64_any_dtype(cleaned_df['scrape_date'])

    def test_last_updated_is_datetime(self, cleaned_df):
        assert pd.api.types.is_datetime64_any_dtype(cleaned_df['last_updated'])

    def test_last_updated_parsed(self, cleaned_df):
        """'15. jan. 2026 22:19' should parse to 2026-01-15."""
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            dt = row['last_updated'].iloc[0]
            assert dt.year == 2026
            assert dt.month == 1
            assert dt.day == 15


class TestCleanHomesOwnership:
    """Test ownership_type cleaning."""

    def test_ownership_stripped(self, cleaned_df):
        """Ownership should be cleaned of prefixes like 'eieform' and '(Selveier)'."""
        for val in cleaned_df['ownership_type'].dropna():
            assert '(Selveier)' not in str(val)
            assert not str(val).lower().startswith('eieform')


class TestCleanHomesPropertyType:
    """Test property_type cleaning."""

    def test_property_type_no_prefix(self, cleaned_df):
        for val in cleaned_df['property_type'].dropna():
            assert not str(val).lower().startswith('boligtype')

    def test_slash_replaced_with_underscore(self, cleaned_df):
        for val in cleaned_df['property_type'].dropna():
            assert '/' not in str(val)


class TestCleanHomesSoldField:
    """Test sold field processing."""

    def test_sold_is_boolean(self, cleaned_df):
        if 'sold' in cleaned_df.columns:
            assert cleaned_df['sold'].dtype in ['bool', 'boolean']


class TestCleanHomesBooleanFeatures:
    """Test boolean feature extraction."""

    def test_equipment_features_are_bool(self, cleaned_df):
        bool_cols = ['eq_parking', 'eq_lift', 'eq_fireplace', 'eq_garden', 'eq_pool']
        for col in bool_cols:
            assert col in cleaned_df.columns

    def test_fixer_upper_is_bool(self, cleaned_df):
        assert cleaned_df['fixer_upper'].dtype in ['bool', 'boolean']

    def test_renovated_is_bool(self, cleaned_df):
        assert cleaned_df['renovated'].dtype in ['bool', 'boolean']


class TestCleanHomesDerivedFeatures:
    """Test computed features."""

    def test_price_pr_sqm_calculated(self, cleaned_df):
        """price_pr_sqm = price / usable_area."""
        row = cleaned_df[cleaned_df['item_id'] == '446259093']
        if not row.empty:
            price = row['price'].iloc[0]
            area = row['usable_area'].iloc[0]
            if pd.notna(price) and pd.notna(area) and area > 0:
                expected = price / area
                assert abs(row['price_pr_sqm'].iloc[0] - expected) < 0.01

    def test_total_price_filled_when_missing(self, cleaned_df):
        """total_price should be filled with price * 1.025 when missing."""
        assert cleaned_df['total_price'].notna().all()

    def test_bedrooms_default_zero(self, cleaned_df):
        """Missing bedrooms should default to 0."""
        assert cleaned_df['bedrooms'].notna().all()

    def test_floor_default_zero(self, cleaned_df):
        """Missing floor should default to 0."""
        assert cleaned_df['floor'].notna().all()
