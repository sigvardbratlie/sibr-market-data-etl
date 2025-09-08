import os
import logging
from http.client import responses
from sibr_module import BigQuery, Logger, SecretsManager
import aiohttp
import asyncio
import inspect
import pandas as pd
from urllib.parse import quote_plus
from typing import Literal
from sibr_api import ApiBase,APIkeyError,RateLimitError,NotFoundError
#from src.settings import GOOGLE_CLOUD_PROJECT
import json
import abc
from dotenv import load_dotenv

class DataApi(ApiBase):
    def __init__(self, logger = None):
        super().__init__(logger_name='nominatim', logger = logger)
        self.bq = BigQuery(project_id = "sibr-market", logger = logger)
        secret = SecretsManager(project_id="sibr-market")
        self.sv_api_key = secret.get_secret("STATENS_VEGVESEN_API_KEY")

    def _encode_address(self, address):

        if "/" in address:
            f = address.split("/")[0]
            l = address.split("/")[1].split(",")
            address = f"{f}, {''.join(l[1:])}"

        encoded_address = quote_plus(address)

        if not isinstance(encoded_address, str) or not encoded_address.strip():
            self.logger.warning(f"Skipping address: {address}. No valid output after encoding: {encoded_address}")
            return None

        return encoded_address

    async def get_nomi(self,address):
        base_url = "https://nominatim.openstreetmap.org/"
        search_endpoint = "search"
        encoded_address = self._encode_address(address)

        if encoded_address is None:
            self.logger.warning(f'Address input is None')
            return None

        url = base_url + search_endpoint + f"?q={encoded_address}&format=jsonv2"
        headers = {'User-Agent': 'YourApp/1.0'}

        proxy_url = self._mk_proxy(url)
        try:
            response = await self.fetch_single(url,headers=headers,proxy_url=proxy_url)
            # if response:
            #     self.ok_responses += 1

            if isinstance(response,dict):
                self.ok_responses += 1
                return response
            elif isinstance(response,list):
                if len(response)==1:
                    self.ok_responses += 1
                    return response[0]
                elif len(response) > 1 :
                    self.ok_responses += 1
                    self.logger.warning(f'Multiple results for address {address}')
                    return response
                else:
                    self.fail_responses += 1
                    self.logger.warning(f'No results for address {address}')
                    return None
            elif response is None:
                self.fail_responses += 1
                self.logger.warning(f'No results for address {address}')
                return None
        except NotFoundError as e:
            self.logger.warning(f'Address {address} not found - 404 error - {e}')
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
                    self.logger.warning(
                        f"Column {col} not found in response. Adding empty column. \t \tresponse: {response}")
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

    async def get_geonorge(self,address):
        base_url = "https://ws.geonorge.no/adresser/v1/"
        search_endpoint = "sok"
        encoded_address = self._encode_address(address)

        if encoded_address is None:
            self.logger.warning(f'Address input is None')
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
                    self.logger.warning(f'Multiple results for address {address}')
                    return response
                else:
                    self.logger.warning(f'No results for address {address}')
                    return None
            elif response is None:
                self.logger.warning(f'No results for address {address}')
                return None
        except NotFoundError as e:
            self.logger.warning(f'Address {address} not found - 404 error - {e}')
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
                self.logger.warning(f'No results {metadata.get("sokeStreng")}') if metadata else self.logger.warning(f'No results for input {item_id}')
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

    def save_func(self,df : pd.DataFrame,table_name : str = None, dataset_name : str = None):

        if table_name is None:
            table_name = "coordinates"
        if dataset_name is None:
            dataset_name = "staging"

        self.bq.to_bq(df = df,
                      table_name = table_name,
                      dataset_name = dataset_name,
                      if_exists = 'merge',
                      merge_on = ['item_id'],
                      explicit_schema = {"get_date": "TIMESTAMP",
                                       "undernummer" : "FLOAT"}
                      )

    async def get_car(self,kjennemerke):
        url = f"https://www.vegvesen.no/ws/no/vegvesen/kjoretoy/felles/datautlevering/enkeltoppslag/kjoretoydata?kjennemerke={kjennemerke}"
        headers = {"SVV-Authorization": f"Apikey {self.sv_api_key}"}
        logging_rate = 500
        try:
            response = await self.fetch_single(url, headers=headers, timeout=30)
            if response:
                self.ok_responses += 1
                if self.ok_responses % logging_rate == 0:
                    self.logger.debug(f'The {logging_rate}th successful response with kjennemerke: {kjennemerke}')
                return response
            else:
                self.fail_responses += 1
                if self.fail_responses % logging_rate == 0:
                    self.logger.error(f'The {logging_rate}th Failed response with kjennemerke: {response.status_code}')
                return None
        except NotFoundError:
            self.fail_responses += 1
            self.logger.warning(f'Car with kjennemerke: {kjennemerke} not found. 404 Error')
            return None

    def transform_singe_car(self, response):
        item_id, res = response
        if res:
            result = res.get('kjoretoydataListe')
            if result and isinstance(result, list):
                base = result[0]
            new_base = {}
            for k, v in base.items():
                if isinstance(v, list) and v:
                    if len(v) == 1:
                        new_base[k] = v[0]
                    else:
                        new_base[k] = v
                else:
                    new_base[k] = v
            df = pd.json_normalize(new_base)
            df["item_id"] = item_id

            def go_deep(df):
                for col in df.columns:
                    e = df[col].iloc[0]
                    if isinstance(e, list) and e:
                        # print(f'Column {col} has is a list')
                        if e:
                            for element in e:
                                if isinstance(element, dict) and element:
                                    for k, v in element.items():
                                        if v:
                                            df[f'{col}_{k}'] = [v]
                                    df.drop(columns=[col], inplace=True, errors='ignore')
                                elif isinstance(element, list) and element:
                                    print(f'Column {col} has is a list within a list')
                    elif isinstance(e, dict) and e:
                        # print(f'Column {col} has is a dict')
                        for k, v in e.items():
                            if v:
                                df[f'{col}_{k}'] = v
                        df.drop(columns=[col], inplace=True, errors='ignore')

            max_len = -float("inf")
            while len(df.columns) > max_len:
                if len(df.columns) > max_len:
                    max_len = len(df.columns)
                go_deep(df)
            self._ensure_fieldnames(df)
            return df
        else:
            df = pd.DataFrame({"item_id": item_id})
            return df

    def transform_cars(self,responses : list):
        if responses:
            res = [self.transform_singe_car(response) for response in responses if response is not None]
            df = pd.concat(res, ignore_index=True)
            self._ensure_fieldnames(df)
            return df

    def save_cars(self,df : pd.DataFrame):
        if not df.empty:
            explicit_schema = {"godkjenning_tekniskGodkjenning_tekniskeData_karosseriOgLasteplan_antallDorer" : ("STRING", "REPEATED")}
            trouble_cols = ["godkjenning_tekniskGodkjenning_tekniskeData_karosseriOgLasteplan_antallDorer"]
            for col in trouble_cols:
                df[col] = df[col].apply(lambda x: x[0] if isinstance(x,list) and len(x)==1 else x)

            self.bq.to_bq(df=df, table_name="statens_vegvesen", dataset_name="staging",if_exists = "replace",explicit_schema=explicit_schema)
            #self.bq.to_bq(df = df, table_name = "statens_vegvesen", dataset_name = "staging", if_exists="merge",merge_on = ["item_id"], explicit_schema=explicit_schema)


if __name__ == '__main__':

    async def main():
        geo  = DataApi()
        sql  = '''
        SELECT h.item_id, h.address
                    FROM `sibr-market.clean.homes` h
                    UNION ALL -- Changed to UNION ALL to keep duplicates if desired, or UNION for unique.
                              -- If you want to ensure item_id is unique across both tables, UNION is fine.
                    SELECT r.item_id, r.address
                    FROM `sibr-market.clean.rentals` r
               '''

        df = geo.bq.read_bq(sql,)
        inputs = df.set_index("item_id")["address"].to_dict()

        results = await geo.get_items_with_ids(inputs,
                                                    fetcher=geo.get_geonorge,
                                               transformer=geo.transformer_geonorge,
                                               save_interval=100,
                                               concurrent_requests=30)
        print(results)
    asyncio.run(main())