import pytest
import pandas as pd
import numpy as np
from fixtures.test_cars_data import raw


@pytest.fixture
def instance(make_clean_instance):
    c = make_clean_instance('cars')
    c.df = pd.DataFrame(raw)
    return c


@pytest.fixture
def cleaned_df(instance):
    return instance.clean_cars()


class TestCleanCarsStructure:
    """Test that clean_cars returns a DataFrame with expected structure."""

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
        expected_eq = [
            'eq_cruise_control', 'eq_parking_sensor_behind', 'eq_parking_sensor_front',
            'eq_rear_view_camera', 'eq_bluetooth', 'eq_tow_hitch', 'eq_360_camera',
            'eq_skin_interior', 'eq_air_conditioning', 'eq_dab', 'eq_apple_carplay',
        ]
        for col in expected_eq:
            assert col in cleaned_df.columns, f"Missing equipment column: {col}"

    def test_has_description_bool_columns(self, cleaned_df):
        assert 'car_for_parts' in cleaned_df.columns
        assert 'timing_belt' in cleaned_df.columns

    def test_has_derived_columns(self, cleaned_df):
        assert 'price_pr_km' in cleaned_df.columns
        assert 'clean_date' in cleaned_df.columns


class TestCleanCarsNumericConversion:
    """Test that string values are properly converted to numeric."""

    def test_total_price_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['total_price'])

    def test_mileage_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['mileage'])

    def test_model_year_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['model_year'])

    def test_power_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['power'])

    def test_weight_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['weight'])

    def test_seats_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['seats'])

    def test_doors_is_numeric(self, cleaned_df):
        assert pd.api.types.is_numeric_dtype(cleaned_df['doors'])

    def test_total_price_parsed_correctly(self, cleaned_df):
        """659 000 kr should become 659000."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['total_price'].iloc[0] == 659000

    def test_mileage_parsed_correctly(self, cleaned_df):
        """33 230 km should become 33230."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['mileage'].iloc[0] == 33230

    def test_power_parsed_correctly(self, cleaned_df):
        """456 hk -> 456."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['power'].iloc[0] == 456


class TestCleanCarsFiltering:
    """Test that data outside valid ranges is removed."""

    def test_total_price_range(self, cleaned_df):
        assert (cleaned_df['total_price'] > 10000).all()
        assert (cleaned_df['total_price'] < 3000000).all()

    def test_mileage_range(self, cleaned_df):
        assert (cleaned_df['mileage'] >= 0).all()
        assert (cleaned_df['mileage'] < 1000000).all()

    def test_model_year_range(self, cleaned_df):
        assert (cleaned_df['model_year'] >= 1900).all()
        assert (cleaned_df['model_year'] < 2030).all()

    def test_seats_range(self, cleaned_df):
        assert (cleaned_df['seats'] >= 0).all()
        assert (cleaned_df['seats'] < 10).all()

    def test_doors_range(self, cleaned_df):
        assert (cleaned_df['doors'] >= 0).all()
        assert (cleaned_df['doors'] < 10).all()


class TestCleanCarsFuelMapping:
    """Test that fuel types are properly mapped."""

    def test_fuel_is_lowercase(self, cleaned_df):
        assert (cleaned_df['fuel'] == cleaned_df['fuel'].str.lower()).all()

    def test_fuel_mapped_values(self, cleaned_df):
        valid_fuels = {'diesel', 'bensin', 'el', 'el + bensin', 'el + diesel', 'hydrogen', 'annet'}
        actual_fuels = set(cleaned_df['fuel'].unique())
        assert actual_fuels.issubset(valid_fuels), f"Unexpected fuels: {actual_fuels - valid_fuels}"

    def test_plugin_bensin_mapped(self, cleaned_df):
        """'Plug-in Bensin' should be mapped to 'el + bensin'."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['fuel'].iloc[0] == 'el + bensin'

    def test_el_mapped(self, cleaned_df):
        """'El' should be mapped to 'el'."""
        row = cleaned_df[cleaned_df['item_id'] == '446252121']
        if not row.empty:
            assert row['fuel'].iloc[0] == 'el'


class TestCleanCarsDatetime:
    """Test datetime handling."""

    def test_scrape_date_is_datetime(self, cleaned_df):
        assert pd.api.types.is_datetime64_any_dtype(cleaned_df['scrape_date'])

    def test_last_updated_is_datetime(self, cleaned_df):
        assert pd.api.types.is_datetime64_any_dtype(cleaned_df['last_updated'])

    def test_last_updated_parsed_norwegian_date(self, cleaned_df):
        """'15. januar 2026, 18:54' should parse to 2026-01-15."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            dt = row['last_updated'].iloc[0]
            assert dt.year == 2026
            assert dt.month == 1
            assert dt.day == 15

    def test_clean_date_is_set(self, cleaned_df):
        assert cleaned_df['clean_date'].notna().all()


class TestCleanCarsGeo:
    """Test geo merging."""

    def test_postal_code_extracted(self, cleaned_df):
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['postal_code'].iloc[0] == '1787'


class TestCleanCarsBooleanFeatures:
    """Test boolean feature extraction from equipment and description."""

    def test_equipment_bool_dtype(self, cleaned_df):
        eq_cols = [c for c in cleaned_df.columns if c.startswith('eq_')]
        for col in eq_cols:
            assert cleaned_df[col].dtype in ['bool', 'boolean', 'object'], f"{col} has unexpected type {cleaned_df[col].dtype}"

    def test_volvo_has_cruise_control(self, cleaned_df):
        """Volvo XC60 features list includes 'Cruisekontroll'."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['eq_cruise_control'].iloc[0] == True

    def test_volvo_has_bluetooth(self, cleaned_df):
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['eq_bluetooth'].iloc[0] == True

    def test_volvo_has_tow_hitch(self, cleaned_df):
        """Volvo XC60 features list includes 'Hengerfeste'."""
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            assert row['eq_tow_hitch'].iloc[0] == True


class TestCleanCarsFillNa:
    """Test default fill values."""

    def test_transfer_fee_filled_if_present(self, cleaned_df):
        if 'transfer_fee' in cleaned_df.columns:
            assert cleaned_df['transfer_fee'].notna().all()

    def test_known_issues_not_null(self, cleaned_df):
        assert cleaned_df['known_issues'].notna().all()

    def test_dealer_not_null(self, cleaned_df):
        assert cleaned_df['dealer'].notna().all()

    def test_liens_is_string(self, cleaned_df):
        if 'liens' in cleaned_df.columns:
            assert cleaned_df['liens'].dtype == 'object' or cleaned_df['liens'].dtype == 'category'


class TestCleanCarsDerivedFeatures:
    """Test computed features."""

    def test_price_pr_km(self, cleaned_df):
        row = cleaned_df[cleaned_df['item_id'] == '446288962']
        if not row.empty:
            expected = row['total_price'].iloc[0] / row['mileage'].iloc[0]
            assert abs(row['price_pr_km'].iloc[0] - expected) < 0.01
