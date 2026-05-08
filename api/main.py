import os
import asyncio
from datetime import datetime
import argparse
from data_warehouse import BigQuery, load_google_credentials
from no_sql import FirestoreDatabase
from dotenv import load_dotenv
from api import DataApi, RateLimitError
from google.cloud import bigquery
from google.cloud import firestore
import logging
from utils import setup_logging
logger = logging.getLogger(__name__)
setup_logging()

load_dotenv()

map_conc_requests = {"nominatim" : 5,
                     "geonorge" : 30}

parser = argparse.ArgumentParser(f'Ceocoding script by SIBR')
group = parser.add_mutually_exclusive_group(required=False)
parser.add_argument('--use-proxy', action='store_true', help='Use proxy for api requests (default: True)')
group.add_argument('--address', type=str, help='Geocode address')
parser.add_argument('--no-save', action='store_true', help='Disable saving results')
parser.add_argument('--limit', type=int, default=None, help='Limit number of rows fetched from SQL (default: None)')
parser.add_argument('--log-level', type=str, default='INFO', help='Logging level (default: INFO)')
parser.add_argument('--cloud-logging', action='store_true', default=False, help='Enable cloud logging (default: False)')
parser.add_argument("--geocoder", choices=["geonorge", "nominatim"], default="geonorge")
parser.add_argument("-t","--task", choices=["geocode","statens-vegvesen","all"],required=True, help="Task to run")

class ApiMain:
    def __init__(self, 
                 api: DataApi, 
                 datawarehouse: BigQuery,
                 nosql_instance: FirestoreDatabase):
        self.api = api
        self.datawarehouse = datawarehouse
        self.nosql_instance = nosql_instance

    async def run_geocoding_new_entries(self, limit : int = None):
        sql = '''
                WITH CombinedItems AS (
                    SELECT h.item_id, h.address
                    FROM `sibr-market.clean.homes` h
                    UNION ALL 
                    SELECT r.item_id, r.address
                    FROM `sibr-market.clean.rentals` r
                    )
                    SELECT ci.item_id, ci.address
                    FROM CombinedItems ci
                    WHERE NOT EXISTS (
                    SELECT 1
                    FROM staging.coordinates c
                    WHERE c.item_id = ci.item_id)
                    '''
        if limit is not None:
            sql += f'\nLIMIT {limit}'

        df = self.datawarehouse.query_to_df(sql)
        inputs = df.set_index("item_id")["address"].to_dict()
        try:
            await self.api.get_items_with_ids(inputs,
                                fetcher=self.api.get_geonorge,
                                transformer=self.api.transformer_geonorge,
                                saver = self.api.save_func,
                                save_interval=5000,
                                concurrent_requests=30,)
        except RateLimitError as e:
            logger.error(f'❌ Rate limit exceeded (Geonorge): {e}')
        finally:
            await self.api.close()

    async def run_geocoding_fill_misses(self, limit : int = None):
        sql = '''
                    SELECT 
                item_id, 
                address
            FROM (
                SELECT item_id, address FROM `sibr-market.clean.homes`
                UNION ALL 
                SELECT item_id, address FROM `sibr-market.clean.rentals`
            ) AS CombinedItems
            WHERE item_id IN (
                SELECT item_id 
                FROM `sibr-market.staging.coordinates`
                WHERE status = "NO_RESULTS" AND geocoder = "geonorge"
            );
        '''

        if limit:
            sql += f'\nLIMIT {limit}'
        df = self.datawarehouse.query_to_df(sql)
        inputs = df.set_index("item_id")["address"].to_dict()
        try:
            await self.api.get_items_with_ids(inputs,
                                fetcher=self.api.get_nomi,
                                transformer=self.api.transformer_nomi,
                                saver = self.api.save_func,
                                save_interval=5000,
                                concurrent_requests=5,)
        except RateLimitError as e:
            logger.error(f'❌ Rate limit exceeded (Nominatim): {e}')
        finally:
            await self.api.close()
                    

    async def run_geocode_address(self, address):
        if not isinstance(address, list):
                addresses = list(address)
        else:
            addresses = address
        result = await self.api.get_geonorge(addresses)
        res = self.api.transform_single_geonorge(result).to_dict(orient='records')[0]
        logger.info(f'🗺️  {address} → {res.get("lat")},{res.get("lng")}')
        return res
    
    async def run_statens_vegvesen(self, limit : int = None):
        #STATENS VEGVESEN har en request limit på 50.000 request pr dag
        limit = min(limit, 50000) if limit else 50000

        fetched_ids = self.nosql_instance.fetch_collection_ids("statens_vegvesen")
        logger.info(f'📋 Already fetched {len(fetched_ids)} items from Statens Vegvesen')
        
        query = """
                SELECT item_id, reg_num
                FROM clean.cars c
                WHERE c.item_id NOT IN UNNEST(@fetched_ids)
                    AND reg_num IS NOT NULL
                """
        if limit:
            query += f'\nLIMIT {limit}'
        params = ("fetched_ids", "STRING", fetched_ids)

        cars = self.datawarehouse.query_to_df(query, params=params)
        cars.set_index("item_id", inplace=True)
        cars_input = cars["reg_num"].to_dict()
        try:
            await self.api.get_items_with_ids(inputs=cars_input,
                                                fetcher=self.api.get_car,
                                                transformer=self.api.transform_cars,
                                                saver=self.api.save_cars,
                                                concurrent_requests=30,
                                                save_interval=9000,
                                                return_result=False)
        except RateLimitError as e:
            logger.error(f'❌ Rate limit exceeded (Statens Vegvesen): {e}')
        finally:
            await self.api.close()

    
async def main(args):
        starttime = datetime.now()
        datawarehouse = BigQuery(credentials=load_google_credentials())
        nosql_instance = FirestoreDatabase(credentials=load_google_credentials())
        api = DataApi(datawarehouse_instance=datawarehouse, no_sql_instance=nosql_instance)
        main_instance = ApiMain(api=api, datawarehouse=datawarehouse, nosql_instance=nosql_instance)

        if args.task in ["geocode","all"]:
            if args.address:
                if args.geocoder == "geonorge":
                    res = await main_instance.run_geocode_address(args.address)
                    print(f'🗺️  {args.address} → {res.get("lat")},{res.get("lng")}')

                else:
                    logger.warning(f'⚠️ Unsupported geocoder {args.geocoder} for single address. Only Geonorge is supported for single address geocoding.')
            else:
                logger.info('🗺️  Starting Geonorge geocoding')
                await main_instance.run_geocoding_new_entries(args.limit)
                
                logger.info('🗺️  Starting Nominatim geocoding — filling Geonorge misses')
                await main_instance.run_geocoding_fill_misses(args.limit)
                
                logger.info(f'✅ Geocoding completed in {datetime.now() - starttime}')
                await main_instance.api.close()
                    
                
        if args.task in ["statens-vegvesen","all"]:
            logger.info('🚗 Starting Statens Vegvesen data fetching')
            await main_instance.run_statens_vegvesen(args.limit)
            

    
if __name__ == "__main__":
    # async def main():
    #     args = parser.parse_args()
    #     starttime = datetime.now()

    #     datawarehouse = BigQuery(credentials=load_google_credentials())
    #     nosql_instance = FirestoreDatabase(credentials=load_google_credentials())
    #     api = DataApi(datawarehouse_instance=datawarehouse, no_sql_instance=nosql_instance)
    #     main_instance = ApiMain(api)

    #     if args.task in ["geocode","all"]:
    #         if args.address:
    #             if args.geocoder == "geonorge":
    #                 res = await main_instance.run_geocode_address(args.address)
    #                 print(f'🗺️  {args.address} → {res.get("lat")},{res.get("lng")}')
    #                 # if not isinstance(args.address, list):
    #                 #     addresses = list(args.address)
    #                 # else:
    #                 #     addresses = args.address
    #                 # result = await api.get_geonorge(addresses)
    #                 # res = api.transform_single_geonorge(result).to_dict(orient='records')[0]
    #                 # logger.info(f'🗺️  {args.address} → {res.get("lat")},{res.get("lng")}')
    #             else:
    #                 logger.warning(f'⚠️ Unsupported geocoder {args.geocoder} for single address. Only Geonorge is supported for single address geocoding.')
    #         else:
    #             logger.info('🗺️  Starting Geonorge geocoding')
    #             main_instance.run_geocoding_new_entries(args.limit)
    #             # sql = '''
    #             #         WITH CombinedItems AS (
    #             #             SELECT h.item_id, h.address
    #             #             FROM `sibr-market.clean.homes` h
    #             #             UNION ALL 
    #             #             SELECT r.item_id, r.address
    #             #             FROM `sibr-market.clean.rentals` r
    #             #             )
    #             #             SELECT ci.item_id, ci.address
    #             #             FROM CombinedItems ci
    #             #             WHERE NOT EXISTS (
    #             #             SELECT 1
    #             #             FROM staging.coordinates c
    #             #             WHERE c.item_id = ci.item_id)
    #             #             '''
    #             # if args.limit:
    #             #     sql += f'\nLIMIT {args.limit}'

    #             # df = datawarehouse.query_to_df(sql)
    #             # inputs = df.set_index("item_id")["address"].to_dict()
    #             # try:
    #             #     await api.get_items_with_ids(inputs,
    #             #                         fetcher=api.get_geonorge,
    #             #                       transformer=api.transformer_geonorge,
    #             #                       saver = api.save_func,
    #             #                         save_interval=5000,
    #             #                         concurrent_requests=30,)
    #             # except RateLimitError as e:
    #             #     logger.error(f'❌ Rate limit exceeded (Geonorge): {e}')
    #             # finally:
    #             #     await api.close()
                
    #             logger.info('🗺️  Starting Nominatim geocoding — filling Geonorge misses')
    #             main_instance.run_geocoding_fill_misses(args.limit)
    #             # sql = '''
    #             #             SELECT 
    #             #         item_id, 
    #             #         address
    #             #     FROM (
    #             #         SELECT item_id, address FROM `sibr-market.clean.homes`
    #             #         UNION ALL 
    #             #         SELECT item_id, address FROM `sibr-market.clean.rentals`
    #             #     ) AS CombinedItems
    #             #     WHERE item_id IN (
    #             #         SELECT item_id 
    #             #         FROM `sibr-market.staging.coordinates`
    #             #         WHERE status = "NO_RESULTS" AND geocoder = "geonorge"
    #             #     );
    #             # '''

    #             # if args.limit:
    #             #     sql += f'\nLIMIT {args.limit}'
    #             # df = datawarehouse.query_to_df(sql)
    #             # inputs = df.set_index("item_id")["address"].to_dict()
    #             # try:
    #             #     await api.get_items_with_ids(inputs,
    #             #                         fetcher=api.get_nomi,
    #             #                       transformer=api.transformer_nomi,
    #             #                       saver = api.save_func,
    #             #                         save_interval=5000,
    #             #                         concurrent_requests=5,)
    #             # except RateLimitError as e:
    #             #     logger.error(f'❌ Rate limit exceeded (Nominatim): {e}')
    #             # finally:
    #                 logger.info(f'✅ Geocoding completed in {datetime.now() - starttime}')
    #                 await api.close()
                    
                
    #     if args.task in ["statens-vegvesen","all"]:
    #         logger.info('🚗 Starting Statens Vegvesen data fetching')
    #         main_instance.run_statens_vegvesen(args.limit)
    #         # #STATENS VEGVESEN har en request limit på 50.000 request pr dag
    #         # if not args.limit:
    #         #     limit = 50000
    #         # else:
    #         #     limit = args.limit

    #         # fetched_ids = nosql_instance.fetch_collection_ids("statens_vegvesen")
    #         # logger.info(f'📋 Already fetched {len(fetched_ids)} items from Statens Vegvesen')
            
    #         # query = """
    #         #         SELECT item_id, reg_num
    #         #         FROM clean.cars c
    #         #         WHERE c.item_id NOT IN UNNEST(@fetched_ids)
    #         #             AND reg_num IS NOT NULL
    #         #         """
    #         # if limit:
    #         #     query += f'\nLIMIT {limit}'
    #         # params = ("fetched_ids", "STRING", fetched_ids)

    #         # cars = datawarehouse.query_to_df(query, params=params)
    #         # cars.set_index("item_id", inplace=True)
    #         # cars_input = cars["reg_num"].to_dict()
    #         # try:
    #         #     await api.get_items_with_ids(inputs=cars_input,
    #         #                                        fetcher=api.get_car,
    #         #                                        transformer=api.transform_cars,
    #         #                                        saver=api.save_cars,
    #         #                                        concurrent_requests=30,
    #         #                                        save_interval=9000,
    #         #                                        return_result=False)
    #         # except RateLimitError as e:
    #         #     logger.error(f'❌ Rate limit exceeded (Statens Vegvesen): {e}')
    #         # finally:
    #         #     await api.close()

    args = parser.parse_args()
    asyncio.run(main(args))