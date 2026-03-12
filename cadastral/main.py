from kartverkets_api.kartverket import kartverketsAPI
from sibr_module import BigQuery
from google.cloud import secretmanager
import logging
import argparse
import asyncio
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
load_dotenv()

if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS is not set.")
    #raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set. Please set it to the path of your Google Cloud credentials JSON file.")

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group(required=True)

group.add_argument("--by-properties", nargs="*", help="gets information about a specific property based on kommunenr, gnr, bnr, festnr & seksjonsnr")
group.add_argument("--by-period", action="store_true", help="gets information about all properties within a given period")
group.add_argument("-up","--update-project", action="store_true", help="Updates status on all properies in the DB")
group.add_argument("-a","--address",type = str, help = "")

parser.add_argument("--start-date", help="The start date for the period (required with --get_by_period)")
parser.add_argument("--end-date", help="The end date for the period (required with --get_by_period)")
parser.add_argument("-t-type","--transfer-type",choices=["active","historical"], help="Transfer type; Choose between active or historical transfers")
parser.add_argument("-s","--save", action="store_true", help="A boolean for storing data to Big Query")
parser.add_argument("-o-type","--ownership-type", type = str, choices=["eier","andel"])
parser.add_argument("-s-num","--section-num", type = int, help = "Section number for the property. Used when asking for single address")
parser.add_argument("-l","--limit", type = int, help = "Limit when reading in data")

type_group  = parser.add_mutually_exclusive_group(required=True)
type_group.add_argument("-f","--fill", action="store_true", help="Fills information for missing rows")
type_group.add_argument("-ow","--overwrite", action="store_true", help="Fills information for missing rows")

secret_client = secretmanager.SecretManagerServiceClient()
os.environ["GRUNNBOK_USERNAME"] = "sibrprod"
os.environ["GRUNNBOK_PASSWORD"] = secret_client.access_secret_version(request={"name": "projects/sibr-market/secrets/GRUNNBOK_API_KEY/versions/latest"}).payload.data.decode("UTF-8")
api = kartverketsAPI()
bq = BigQuery(logger=logger,project_id="sibr-market")


async def main():

    starttime = datetime.now()
    args = parser.parse_args()

    try:
        if args.by_properties:
            try:
                df = await api.get_by_property(args.by_properties, transfer_type=args.transfer_type)
                if args.save_bq:
                    trouble_columns = [
                        #  "oppdateringsdato_timestamp",
                        # "endretavids_cachedvalue_item",
                        "omsetning_omsatteregisterenhetsretter_item"
                    ]
                    for col in trouble_columns:
                        df[col] = df[col].astype(str)
                    bq.to_bq(df=df,
                             dataset_name = "admin",
                             table_name = "kartverket")
            except Exception as e:
                logger.error(f'❌ Error getting properties from by_properties: {e}')

        elif args.by_period:
            if args.start_date and args.end_date:
                api.get_by_period(args.start_date, args.end_date)

        elif args.update_project:
            BATCH_SIZE = 50000
            transfer_type_arg = [args.transfer_type] if args.transfer_type else ["active", "historical"]
            ownership_type_arg = [args.ownership_type] if args.ownership_type else ["eier", "andel",]
            if args.overwrite:
                transfer_type_arg = ["active"]
            #max_date = bq.read_bq("SELECT MAX (scrape_date) FROM raw.homes")
            #max_date = max_date.iloc[0,0]
            max_date = None
            logger.info(f'🚀 Updating project | ownership={ownership_type_arg} | transfer={transfer_type_arg} | fill={args.fill} | overwrite={args.overwrite} | batch={BATCH_SIZE} | limit={args.limit}')
            for transfer_type in transfer_type_arg:
                for ownership_type in ownership_type_arg:
                    if ownership_type == "eier":
                        query = f"""
                                SELECT item_id,
                                       municipality_num,
                                       cadastral_num,
                                       unit_num,
                                       leasehold_num,
                                       section_num
                                FROM `sibr-market.clean.homes` h
                                WHERE cadastral_num IS NOT NULL
                                  AND unit_num IS NOT NULL
                                  --AND DATE (scrape_date) != {max_date}
                                  AND LOWER (ownership_type) = 'eier'
                                """
                        request_cols = ["kommunenummer", "gaardsnummer", "bruksnummer", "festenummer", "seksjonsnummer"]
                    elif ownership_type == "andel":
                        query = f"""
                                SELECT item_id,
                                       coop_unit_num,
                                       coop_org_num
                                FROM `sibr-market.clean.homes` h
                                WHERE coop_unit_num IS NOT NULL
                                  AND coop_org_num IS NOT NULL
                                  --AND DATE (scrape_date) != {max_date}
                                  AND LOWER (ownership_type) = 'andel'
                                """
                        request_cols = ["borettslagnummer", "andelsnummer"]
                    else:
                        raise TypeError(f'Expected "eier" or "andel" but got {ownership_type}')

                    if args.fill:
                        query += f"""\nAND NOT EXISTS (SELECT 1 
                                                  FROM staging.cadastrals c 
                                                  WHERE c.item_id = h.item_id AND c.active = {transfer_type == 'active'})"""
                    elif args.overwrite:
                        query += f'\nAND DATE(scrape_date) > DATE_SUB(CURRENT_DATE(), INTERVAL 300 DAY)'
                    if args.limit:
                        query += f"\nLIMIT {args.limit}"
                    logger.info(f'📥 Reading from BQ — transfer={transfer_type}, ownership={ownership_type}')
                    #print(query)
                    db = bq.read_bq(query)

                    #TRANSFORM DATA FOR KARTVERKET
                    db = api.transform_cadastrals(db, request_cols=request_cols) if ownership_type == "eier" else api.transform_coop(db,request_cols=request_cols)
                    properties = db[request_cols].to_dict(orient='records')
                    logger.info(f'📊 Total properties to process: {len(properties)}')
                    #logger.warning(f'EXAMPLE: {properties[:5]}')
                    for batch in range(0,len(properties),BATCH_SIZE):
                        logger.info(f'🔄 Batch {batch//BATCH_SIZE + 1}: {len(properties[batch:batch+BATCH_SIZE])} of {len(properties)} properties ({len(properties[batch:batch+BATCH_SIZE]) / len(properties) * 100:.1f}%)')
                        try:
                            df = await api.get_by_property(properties[batch:batch+BATCH_SIZE], transfer_type=transfer_type, ownership_type=ownership_type)
                        except Exception as e:
                            logger.error(f'❌ Error in get_by_property (batch {batch}): {e}')
                            raise

                        logger.info(f'➡️ Input from batch kartverket API to data cleaning: {len(df)} with transfer type {transfer_type} and ownership type {ownership_type}')
                        
                        view = api.trim_output(df = df, db=db, request_cols=request_cols,transfer_type=transfer_type)
                        logger.info(f'⬅️  Output from data cleaning: {len(view)}')
                        if args.save:
                            bq.to_bq(df=view,
                                     table_name = "cadastrals",
                                     dataset_name = "staging",
                                     if_exists = "merge",
                                     #if_exists="replace",
                                     merge_on = ["id_value"],
                                     explicit_schema = {"get_date" : "TIMESTAMP"}
                                     )
                            query_to_exe = """MERGE INTO `sibr-market.staging.cadastrals` T
                                                                            USING (
                                                                              SELECT id_value
                                                                              FROM (
                                                                                SELECT
                                                                                  id_value,
                                                                                  ROW_NUMBER() OVER(PARTITION BY item_id ORDER BY get_date DESC) as rn
                                                                                FROM `sibr-market.staging.cadastrals`
                                                                                WHERE active = TRUE
                                                                              )
                                                                              WHERE rn > 1 -- Finn alle som IKKE er den nyeste (rn=1)
                                                                            ) S
                                                                            ON T.id_value = S.id_value
                                                                            WHEN MATCHED THEN
                                                                              UPDATE SET active = FALSE;"""
                            bq.exe_query(query_to_exe)

    except Exception as e:
        logger.error(f'❌ Unexpected error: {e}')

    finally:
        logger.info(f'✅ Program finished in {datetime.now() - starttime}')
        await api.close()

if __name__ == "__main__" :
    asyncio.run(main())