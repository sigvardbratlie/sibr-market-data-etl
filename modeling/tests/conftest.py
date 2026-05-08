import pytest
import pandas as pd
import sys
import os
from unittest.mock import patch, MagicMock

# Ensure the modeling and tests directories are on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from modeling.cleaning import CarsCleaner, HomesCleaner, RentalsCleaner, NewHomesCleaner
from modeling.base import SibrBase

_CLEANER_MAP = {
    'cars': CarsCleaner,
    'homes': HomesCleaner,
    'rentals': RentalsCleaner,
    'new_homes': NewHomesCleaner,
}


GEO_DATA = pd.DataFrame({
    'postal_code': [
        # Cars
        '1787', '6260', '3060', '7540',
        # Homes
        '1598', '2414', '0483', '7091', '1920', '3271', '7514',
        # New homes
        '4841', '6718', '2817', '4656', '2030',
        # Rentals
        '4275', '7512', '4612', '2318', '2821', '5363', '6450', '0354', '5365',
    ],
    'municipality': [
        'Halden', 'Sula', 'Drammen', 'Trondheim',
        'Moss', 'Elverum', 'Oslo', 'Trondheim', 'Lillestrøm', 'Larvik', 'Stjørdal',
        'Arendal', 'Vågsøy', 'Gjøvik', 'Kristiansand', 'Nannestad',
        'Karmøy', 'Stjørdal', 'Kristiansand', 'Hamar', 'Gjøvik', 'Øygarden', 'Molde', 'Oslo', 'Øygarden',
    ],
    'county': [
        'Østfold', 'Møre og Romsdal', 'Buskerud', 'Trøndelag',
        'Østfold', 'Innlandet', 'Oslo', 'Trøndelag', 'Akershus', 'Vestfold', 'Trøndelag',
        'Agder', 'Vestland', 'Innlandet', 'Agder', 'Akershus',
        'Rogaland', 'Trøndelag', 'Agder', 'Innlandet', 'Innlandet', 'Vestland', 'Møre og Romsdal', 'Oslo', 'Vestland',
    ],
    'region': [
        'Østlandet', 'Vestlandet', 'Østlandet', 'Midt-Norge',
        'Østlandet', 'Østlandet', 'Østlandet', 'Midt-Norge', 'Østlandet', 'Østlandet', 'Midt-Norge',
        'Sørlandet', 'Vestlandet', 'Østlandet', 'Sørlandet', 'Østlandet',
        'Vestlandet', 'Midt-Norge', 'Sørlandet', 'Østlandet', 'Østlandet', 'Vestlandet', 'Vestlandet', 'Østlandet', 'Vestlandet',
    ],
})


def _make_clean_instance(dataset: str):
    """Create a cleaner instance with mocked external dependencies (no GCP calls)."""
    CleanerClass = _CLEANER_MAP[dataset]
    with patch.object(SibrBase, 'setup'):
        instance = CleanerClass(logger=MagicMock())
    instance.geo = GEO_DATA.copy()
    return instance


@pytest.fixture
def make_clean_instance():
    """Factory fixture for creating Clean instances without GCP dependencies."""
    return _make_clean_instance
