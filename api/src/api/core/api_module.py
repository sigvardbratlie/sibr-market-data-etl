import asyncio
import pandas as pd
import os
from urllib.parse import quote_plus

from google.cloud import firestore,secretmanager
from concurrent.futures import ThreadPoolExecutor

from .api_base import ApiBase, NotFoundError
from api.data_warehouse import DataBase
from api.no_sql import NoSQLDatabase

import logging

logger = logging.getLogger(__name__)

class DataApi(ApiBase):
    def __init__(self,
                 datawarehouse_instance : DataBase,
                 no_sql_instance : NoSQLDatabase,
                 ):
        super().__init__()
        self.database =datawarehouse_instance
        self.nosql = no_sql_instance
    
    def _encode_address(self, address):

        if "/" in address:
            f = address.split("/")[0]
            l = address.split("/")[1].split(",")
            address = f"{f}, {''.join(l[1:])}"

        encoded_address = quote_plus(address)

        if not isinstance(encoded_address, str) or not encoded_address.strip():
            logger.warning(f"⚠️ Skipping invalid address: '{address}'")
            return None

        return encoded_address

    def save_func(self,df : pd.DataFrame, table_name : str = None, dataset_name : str = None):

        if table_name is None:
            table_name = "coordinates"
        if dataset_name is None:
            dataset_name = "staging"

        self.database.save_table(df = df,
                      table_name = table_name,
                      dataset_name = dataset_name,
                      if_exists = 'merge',
                      merge_on = ['item_id'],
                      explicit_schema = {"get_date": "TIMESTAMP",
                                       "undernummer" : "FLOAT"}
                      )

    # ====== NOMIMATIM ======
    async def get_nomi(self,address):
        base_url = "https://nominatim.openstreetmap.org/"
        search_endpoint = "search"
        encoded_address = self._encode_address(address)

        if encoded_address is None:
            logger.warning("⚠️ Address input is None")
            return None

        url = base_url + search_endpoint + f"?q={encoded_address}&format=jsonv2"
        headers = {'User-Agent': 'YourApp/1.0'}

        proxy_url = self._mk_proxy(url)
        try:
            response = await self.fetch_single(url,headers=headers,proxy_url=proxy_url)

            if isinstance(response,dict):
                self.ok_responses += 1
                return response
            elif isinstance(response,list):
                if len(response)==1:
                    self.ok_responses += 1
                    return response[0]
                elif len(response) > 1 :
                    self.ok_responses += 1
                    logger.warning(f"⚠️ Multiple results for address: '{address}'")
                    return response
                else:
                    self.fail_responses += 1
                    logger.warning(f"⚠️ No results for address: '{address}'")
                    return None
            elif response is None:
                self.fail_responses += 1
                logger.warning(f"⚠️ No results for address: '{address}'")
                return None
        except NotFoundError as e:
            logger.warning(f"⚠️ Address not found (404): '{address}'")
            self.fail_responses += 1
            return None

    def transform_single_nomi(self,response : tuple[str,dict] | dict) -> pd.DataFrame:
        required_cols = ['item_id', 'lat', 'lng', 'status', 'geocoder', 'adressetekst' ,'get_date']
        if isinstance(response,tuple):
            item_id = response[0]
            json_data = response[1]
        elif isinstance(response,dict):
            json_data = response
            item_id = None
        else:
            raise TypeError(f'Not valid response type. Expected tuple or dict, but got {type(response)}')

        if json_data is not None:
            data = pd.json_normalize(json_data)
            data.rename(columns={'lon': 'lng',
                                 'display_name': 'adressetekst',
                                 'name': 'adressenavn',
                                 "addresstype": "objtype"}, inplace=True)
            data['item_id'] = item_id
            data['status'] = "OK"
            data['lat'] = pd.to_numeric(data['lat'], errors='coerce')
            data['lng'] = pd.to_numeric(data['lng'], errors='coerce')
            data['geocoder'] = "nominatim"
            data['get_date'] = pd.Timestamp.now()

            for col in required_cols:
                if col not in data.columns:
                    logger.warning(
                        f"⚠️ Column '{col}' not in response — adding empty. Response: {response}")
                    data[col] = None
            return data[required_cols]

        elif json_data is None and item_id is not None:
            return pd.DataFrame({'item_id': [item_id],
                                 'status': 'NO_RESULTS',
                                 'geocoder': "nominatim",
                                 'get_date': pd.Timestamp.now()
                                 })

    def transformer_nomi(self,results : list):
        if results:
            dfs = [self.transform_single_nomi(result) for result in results if result is not None]
            df = pd.concat(dfs, ignore_index=True)
            self._ensure_fieldnames(df)
            return df

    # ====== GEONORGE ===========

    async def get_geonorge(self,address):
        base_url = "https://ws.geonorge.no/adresser/v1/"
        search_endpoint = "sok"
        encoded_address = self._encode_address(address)

        if encoded_address is None:
            logger.warning("⚠️ Address input is None")
            return None

        url = f"{base_url}{search_endpoint}?sok={encoded_address}"
        headers = None
        proxy_url = self._mk_proxy(url)

        try:
            response = await self.fetch_single(url,headers=headers,proxy_url=proxy_url)

            if isinstance(response, dict):
                return response
            if isinstance(response, list):
                if len(response) == 1:
                    return response[0]
                elif len(response) > 1:
                    logger.warning(f"⚠️ Multiple results for address: '{address}'")
                    return response
                else:
                    logger.warning(f"⚠️ No results for address: '{address}'")
                    return None
            elif response is None:
                logger.warning(f"⚠️ No results for address: '{address}'")
                return None
        except NotFoundError as e:
            logger.warning(f"⚠️ Address not found (404): '{address}'")
            return None

    def transform_single_geonorge(self,response : tuple[str,dict] | dict) -> pd.DataFrame:
        if isinstance(response, tuple):
            item_id = response[0]
            json_data = response[1]
        elif isinstance(response, dict):
            json_data = response
            item_id = None
        else:
            raise TypeError(f'Not valid response type. Expected tuple or dict, but got {type(response)}')

        if json_data:
            addresses = json_data.get("adresser", [])
            metadata = json_data.get("metadata", {})

            all_data = []
            for addr in addresses:
                geo = addr.get("representasjonspunkt")
                merged_data = {**addr, **metadata, **geo}
                all_data.append(merged_data)
            df = pd.DataFrame(all_data)
            df['item_id'] = item_id
            df['get_date'] = pd.Timestamp.now()
            df["status"] = "OK"
            df["geocoder"] = "geonorge"
            if "representasjonspunkt" in df.columns:
                df["representasjonspunkt"] = df["representasjonspunkt"].astype(str)
            df.rename(columns={"lon" : "lng"},inplace=True)
            if not df.empty:
                self.ok_responses += 1
                return df
            elif df.empty:
                self.fail_responses += 1
                logger.debug(f"⚠️ No geocode results for: {metadata.get('sokeStreng') if metadata else item_id}")
                if item_id is not None:
                    return pd.DataFrame({"item_id": [item_id],
                                 "get_date": pd.Timestamp.now(),
                                 "status": "NO_RESULTS",
                                 "geocoder": "geonorge"})
        else:
            self.fail_responses += 1
            if item_id is not None:
                return pd.DataFrame({"item_id": [item_id],
                                     "get_date": pd.Timestamp.now(),
                                     "status": "NO_RESULTS",
                                     "geocoder": "geonorge"})

    def transformer_geonorge(self,results : list):
        if results:
            dfs = [self.transform_single_geonorge(result) for result in results if result is not None]
            df = pd.concat(dfs, ignore_index=True)
            self._ensure_fieldnames(df)
            return df


    # ===== STATENS VEGVESEN ========
    async def get_car(self,kjennemerke):
        url = f"https://www.vegvesen.no/ws/no/vegvesen/kjoretoy/felles/datautlevering/enkeltoppslag/kjoretoydata?kjennemerke={kjennemerke}"
        headers = {"SVV-Authorization": f"Apikey {os.getenv('STATENS_VEGVESEN_API_KEY')}"}
        logging_rate = 500
        try:
            response = await self.fetch_single(url, headers=headers, timeout=30)
            if response:
                self.ok_responses += 1
                if self.ok_responses % logging_rate == 0:
                    logger.debug(f'The {logging_rate}th successful response with kjennemerke: {kjennemerke}')
                return response
            else:
                self.fail_responses += 1
                if self.fail_responses % logging_rate == 0:
                    logger.error(f"❌ {logging_rate}th failed response for kjennemerke: {kjennemerke}")
                return None
        except NotFoundError:
            self.fail_responses += 1
            logger.warning(f"⚠️ Car not found (404): kjennemerke={kjennemerke}")
            return None

    def transform_cars(self,responses : list):
        return responses
    
    def commit_batch(self, batch):
        try:
            batch.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Batch commit failed: {e}")
            return False

    def save_cars(self, responses, batch_size=200):
        self.nosql.save_response(responses, batch_size=batch_size)
