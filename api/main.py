import os
import asyncio
from datetime import datetime
import argparse
from dotenv import load_dotenv
from pathlib import Path
from src.api import DataApi
from sibr_api import RateLimitError
from sibr_module import Logger
from google.cloud import bigquery
from google.cloud import firestore

load_dotenv()

if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set. Please set it to the path of your Google Cloud credentials JSON file.")


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
#parser.add_argument('--api', type=str, default='nominatim', help='Geocoding API to use (default: nominatim)')
parser.add_argument("--geocoder", choices=["geonorge", "nominatim"], default="geonorge")
parser.add_argument("-t","--task", choices=["geocode","statens-vegvesen","all"],required=True, help="Task to run")

if __name__ == "__main__":
    async def main():
        args = parser.parse_args()
        logger = Logger(log_name='api',enable_cloud_logging=args.cloud_logging)
        starttime = datetime.now()

        api = DataApi(logger=logger)

        if args.task in ["geocode","all"]:
            if args.address:
                if args.geocoder == "geonorge":
                    if not isinstance(args.address, list):
                        addresses = list(args.address)
                    else:
                        addresses = args.address
                    result = await api.get_geonorge(addresses)
                    res = api.transform_single_geonorge(result).to_dict(orient='records')[0]
                    print(f'Coordinates for address {args.address}: {res.get("lat")},{res.get("lng")}')
            else:
                logger.info(f'====== STARTING GEONORGE GEOCODING ======')
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
                if args.limit:
                    sql += f'\nLIMIT {args.limit}'

                df = api.bq.read_bq(sql)
                inputs = df.set_index("item_id")["address"].to_dict()
                try:
                    await api.get_items_with_ids(inputs,
                                        fetcher=api.get_geonorge,
                                      transformer=api.transformer_geonorge,
                                      saver = api.save_func,
                                        save_interval=5000,
                                        concurrent_requests=30,)
                except RateLimitError as e:
                    logger.error(f'Rate limit exceeded: {e}. Stopping script. Please try again later')
                finally:
                    await api.close()
                logger.info(f'====== STARTING NOMINATIM GEOCODING ======\n \tfetching those items that Geonorge missed!')
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

                if args.limit:
                    sql += f'\nLIMIT {args.limit}'
                df = api.bq.read_bq(sql)
                inputs = df.set_index("item_id")["address"].to_dict()
                try:
                    await api.get_items_with_ids(inputs,
                                        fetcher=api.get_nomi,
                                      transformer=api.transformer_nomi,
                                      saver = api.save_func,
                                        save_interval=5000,
                                        concurrent_requests=5,)
                except RateLimitError as e:
                    logger.error(f'Rate limit exceeded: {e}. Stopping script. Please try again later')
                finally:
                    logger.info(f'Geocoding process completed. Time used: {datetime.now() - starttime}.')
                    await api.close()

        if args.task in ["statens-vegvesen","all"]:
            #STATENS VEGVESEN har en request limit på 50.000 request pr dag
            bq_client = bigquery.Client()
            db = firestore.Client(project="sibr-market", database="backend")
            if not args.limit:
                limit = 50000
            else:
                limit = args.limit

            fetched_ids = db.collection("statens_vegvesen").list_documents()
            fetched_ids = [doc.id for doc in fetched_ids]
            logger.info(f'Already fetched {len(fetched_ids)} items from Statens Vegvesen API')
            query = """
                    SELECT item_id, reg_num
                    FROM clean.cars c
                    WHERE c.item_id NOT IN UNNEST(@fetched_ids)
                        AND reg_num IS NOT NULL
                    """
            if limit:
                query += f'\nLIMIT {limit}'
            params = [
                bigquery.ArrayQueryParameter(
                    "fetched_ids", "STRING", fetched_ids
                )
            ]

            cars = bq_client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).to_dataframe()
            cars.set_index("item_id", inplace=True)
            cars_input = cars["reg_num"].to_dict()
            try:
                await api.get_items_with_ids(inputs=cars_input,
                                                   fetcher=api.get_car,
                                                   transformer=api.transform_cars,
                                                   saver=api.save_cars,
                                                   concurrent_requests=30,
                                                   save_interval=9000,
                                                   return_result=False)
            except RateLimitError as e:
                logger.error(f'Rate limit exceeded: {e}. Stopping script. Please try again later')
            finally:
                await api.close()

    asyncio.run(main())