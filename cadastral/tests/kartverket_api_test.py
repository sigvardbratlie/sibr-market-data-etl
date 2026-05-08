import pytest
import pandas as pd
import zeep.exceptions
from dotenv import load_dotenv
import pytest_asyncio
from unittest.mock import patch,MagicMock,AsyncMock
from kartverkets_api.kartverket import kartverketsAPI
import os
from collections import OrderedDict
import datetime
from decimal import Decimal


os.chdir("..")
load_dotenv()

# === TEST PROP ID ====
@patch("src.kartverkets_api.kartverket.zeep.Client")
def test_get_propId_success(mock_ident_client):
    properties = [{"kommunenummer": "0301",
                   "gaardsnummer": 207,
                   "bruksnummer": 167,
                   "festenummer": 0,
                   "seksjonsnummer": 0}]

    RESPONSE_MATRIKKELENHET = {
        'kommunenummer': '0301',
        'gaardsnummer': 207,
        'bruksnummer': 167,
        'festenummer': 0,
        'seksjonsnummer': 0
    }
    RESPONSE_PROP_ID = [{
        'key': {
            'kommunenummer': '0301',
            'gaardsnummer': 207,
            'bruksnummer': 167,
            'festenummer': 0,
            'seksjonsnummer': 0
        },
        'value': {
            'value': '1359679'
        }
    }]

    mock_instance = MagicMock()
    mock_factory = MagicMock()
    mock_factory.MatrikkelenhetIdent.return_value = RESPONSE_MATRIKKELENHET

    mock_instance.service.findRegisterenhetIdsForIdents.return_value = RESPONSE_PROP_ID
    mock_instance.type_factory.return_value = mock_factory
    mock_ident_client.return_value = mock_instance #erstatter zeep.Client med mock instances


    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    result = api._get_propertyIds(properties,ownership_type="eier")
    mock_instance.service.findRegisterenhetIdsForIdents.assert_called_once()
    mock_instance.type_factory.assert_called_once()

    expected_result = [({'kommunenummer': '0301',
   'gaardsnummer': 207,
   'bruksnummer': 167,
   'festenummer': 0,
   'seksjonsnummer': 0},
  '1359679')]
    assert result == expected_result

@patch("src.kartverkets_api.kartverket.zeep.Client")
def test_get_propId_not_found(mock_ident_client):
    properties = [{"kommunenummer": "301",
                   "gaardsnummer": 207,
                   "bruksnummer": 167,
                   "festenummer": 0,
                   "seksjonsnummer": 0}]

    RESPONSE_MATRIKKELENHET = {
        'kommunenummer': '301',
        'gaardsnummer': 207,
        'bruksnummer': 167,
        'festenummer': 0,
        'seksjonsnummer': 0
    }
    RESPONSE_PROP_ID = [{
        'key': {
            'kommunenummer': '0301',
            'gaardsnummer': 207,
            'bruksnummer': 167,
            'festenummer': 0,
            'seksjonsnummer': 0
        },
        'value': None
    }]

    mock_instance = MagicMock()
    mock_factory = MagicMock()
    mock_factory.MatrikkelenhetIdent.return_value = RESPONSE_MATRIKKELENHET

    mock_instance.service.findRegisterenhetIdsForIdents.return_value = RESPONSE_PROP_ID
    mock_instance.type_factory.return_value = mock_factory
    mock_ident_client.return_value = mock_instance  # erstatter zeep.Client med mock instances


    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    result = api._get_propertyIds(properties,ownership_type="eier")
    mock_instance.service.findRegisterenhetIdsForIdents.assert_called_once()
    mock_instance.type_factory.assert_called_once()

    assert result == []


# === TEST TRANSFER ID ====
@pytest.fixture
def mock_rettsstiftelse_client_success():
    with patch("src.kartverkets_api.kartverket.AsyncClient") as client:
        mock_instance = MagicMock()
        mock_factory = MagicMock()
        mock_zeep_object = MagicMock()
        mock_zeep_object.value = '1359679'
        mock_factory.RegisterenhetId.return_value = mock_zeep_object

        return_value = [{'key': {'value': '109913796'},
             'value': {'value': '140301929'}}
        ]
        mock_instance.service.findOverdragelserMedAktiveAndelerIRegisterenhet = AsyncMock(return_value = return_value)

        mock_instance.type_factory.return_value = mock_factory
        client.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_get_single_transId_sucsess(mock_rettsstiftelse_client_success):
    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    res = await api._get_single_transId_by_propertyId(client = mock_rettsstiftelse_client_success, id = '1359679', transfer_type = "active")

    expected_result = [
            {'key': {'value': '109913796'},
             'value': {'value': '140301929'}}
        ]
    mock_rettsstiftelse_client_success.service.findOverdragelserMedAktiveAndelerIRegisterenhet.assert_awaited_once()

    assert res == expected_result

@patch.object(kartverketsAPI, '_get_single_transId_by_propertyId', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_get_transId_sucsess(mock_single):

    return_value = [
        {'key': {'value': '109913796'},
         'value': {'value': '140301929'}}
    ]
    mock_single.return_value = return_value

    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    input_ids = ['1359679']
    res = await api._get_transferIds_by_propertyIds(input_ids)

    expected_result = {'1359679': {'andel_ids': ['109913796'], 'overdragelse_ids': ['140301929'],}}

    mock_single.assert_awaited_once()
    assert res == expected_result



@pytest.fixture
def mock_rettsstiftelse_client_failure():
    with patch("src.kartverkets_api.kartverket.AsyncClient") as client:
        mock_instance = MagicMock()
        mock_factory = MagicMock()
        mock_zeep_object = MagicMock()
        mock_zeep_object.value = '1359679'
        mock_factory.RegisterenhetId.return_value = mock_zeep_object

        return_value = zeep.exceptions.Fault(message="test error")
        mock_instance.service.findOverdragelserMedAktiveAndelerIRegisterenhet = AsyncMock(side_effect = return_value)

        mock_instance.type_factory.return_value = mock_factory
        client.return_value = mock_instance
        yield mock_instance
@pytest.mark.asyncio
async def test_get_single_transId_fail(mock_rettsstiftelse_client_failure):
    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    with pytest.raises(zeep.exceptions.Fault):
        await api._get_single_transId_by_propertyId(client = mock_rettsstiftelse_client_failure, id = '13596790', transfer_type = "active")


# === TEST INFO BY TRANSFER ID ====

@patch("src.kartverkets_api.kartverket.zeep.Client")
def test_get_info_by_transferIds_success(mock_store_client):

    overdragelse_input = ['140301929']

    mock_instance = MagicMock()
    mock_factory = MagicMock()
    mock_factory.MatrikkelenhetIdent.return_value = {'value': '140301929'}

    return_value = [
        {
            'id': {'value': '140301929'},
            'dokumentId': {'value': '86546948'},
            'omsetning': {
                'id': 140303986,
                'vederlag': {
                    'beloepsverdi': Decimal('85000000'),
                }
            }
        }
    ]
    mock_instance.service.getObjects.return_value = return_value
    mock_instance.type_factory.return_value = mock_factory
    mock_store_client.return_value = mock_instance  # erstatter zeep.Client med mock instances

    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    result = api._get_info_by_transferIds(overdragelse_input)

    mock_instance.service.getObjects.assert_called_once()

    assert result == return_value


@patch("src.kartverkets_api.kartverket.zeep.Client")
def test_get_info_by_transferIds_failure(mock_store_client):

    overdragelse_input = ['140301929']

    mock_instance = MagicMock()
    mock_factory = MagicMock()
    mock_factory.MatrikkelenhetIdent.return_value = {'value': '140301929'}

    return_value = zeep.exceptions.Fault(message="test feil")
    mock_instance.service.getObjects.return_value = return_value
    mock_instance.type_factory.return_value = mock_factory
    mock_store_client.return_value = mock_instance  # erstatter zeep.Client med mock instances

    api = kartverketsAPI()
    api.username = "test_username"
    api.password = "test_password"

    result = api._get_info_by_transferIds(overdragelse_input)

    assert result == []