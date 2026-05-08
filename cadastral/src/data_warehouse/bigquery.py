import pandas as pd
import uuid
import traceback
from typing import Literal
import logging
import os
import json
from google.oauth2 import service_account
from google.cloud import bigquery
from abc import ABC, abstractmethod
from base64 import b64decode
from .base import DataBase

logger = logging.getLogger(__name__)

def load_google_credentials():
    string = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    decoded_bytes = b64decode(string.encode("utf-8"))
    json_content = decoded_bytes.decode("utf-8")
    credentials = service_account.Credentials.from_service_account_info(json.loads(json_content))
    return credentials

class BigQuery(DataBase):
    """A helper class for interacting with Google BigQuery.

        This class simplifies common BigQuery operations such as uploading
        pandas DataFrames to tables and running SQL queries to fetch data.
        It includes built-in logic for 'append', 'replace', and 'merge' operations.

        Attributes:
            project (str): The Google Cloud project ID associated with the client.
        """
    def __init__(self, 
                 credentials = None) -> None:
        '''
        Initialize a BigQuery client.
        Args:    
            dataset : str - Default dataset to use for queries and uploads. Optional.

        Returns:
            None
        '''
        self._bq_client = bigquery.Client(credentials=credentials)
        
    def save_table(self,
              df : pd.DataFrame,
              table_name : str,
              dataset_name : str,
              if_exists: Literal['append', 'replace', 'merge'] = 'append',
              to_str=False,
              merge_on=None,
              autodetect : bool = False,
              dtype_map : dict = None,
              explicit_schema : dict = None) -> None:
        '''
        Save a DataFrame to BigQuery.
        :param df:
        :param table_name:
        :param dataset_name:
        :param if_exists: Choose between 'append', 'replace', or 'merge'.
        :param to_str: Optional to convert all columns to string.
        :param merge_on: Required with if_exists = 'merge'.
        :param autodetect: boolean.
        :param dtype_map: Optional. Add a map from datatypes to desired BigQuery types as a dictionary. Examples: dtype_map = {'object': 'STRING','string': 'STRING','int64': 'INTEGER'}
        :param explicit_schema: Optional. Add desired types to specific columns in your dataframe.
        :return:

        The default dtype_map is defined as
            dtype_map = {
                'object': 'STRING',
                'string': 'STRING',
                'category': 'STRING',
                'str': 'STRING',
                'list': ("STRING", "REPEATED"),
                'int64': 'INTEGER',
                'Int64': 'INTEGER',
                'int64[pyarrow]': 'INTEGER',
                'float32' : 'FLOAT',
                'Float32' : 'FLOAT',
                'float64': 'FLOAT',
                'Float64': 'FLOAT',
                'bool': 'BOOLEAN',
                'boolean': 'BOOLEAN',
                'decimal.Decimal': "NUMERIC",
                'Decimal': "NUMERIC",
                'datetime64[ns]': 'DATETIME',
                'datetime': 'DATETIME',
                'datetime64[ns, UTC]': 'TIMESTAMP',
                'Timestamp': 'TIMESTAMP',
                'date32[day][pyarrow]': 'DATE',
                'datetime64[us]': 'DATETIME',
            }
        '''
        dataset_id = f'{self.project}.{dataset_name}'
        table_id = f"{dataset_id}.{table_name}"
        if if_exists not in ['append', 'replace', 'merge']:
            raise TypeError(f"Invalid if_exists value: {if_exists}. Choose between 'append', 'replace', or 'merge'.")
        if dtype_map is not None and not isinstance(dtype_map, dict):
            raise TypeError(f"Invalid dtype_map value: {dtype_map}. Expected a dictionary.")
        if explicit_schema is not None and not isinstance(explicit_schema, dict):
            raise TypeError(f"Invalid explicit_schema value: {explicit_schema}. Expected a dictionary.")

        try:
            self._bq_client.get_table(table_id)
            table_exists = True
        except Exception:
            table_exists = False

        schema = None
        column_to_bq_type = {}
        if not autodetect:
            if dtype_map is None:
                dtype_map = {
                    'object': 'STRING',
                    'string': 'STRING',
                    'category': 'STRING',
                    'str': 'STRING',
                    'list': ("STRING", "REPEATED"),
                    "ndarray" : ("STRING", "REPEATED"),
                    'int' : 'INTEGER',
                    'int64': 'INTEGER',
                    'Int64': 'INTEGER',
                    'int64[pyarrow]': 'INTEGER',
                    'float' : 'FLOAT',
                    'float32': 'FLOAT',
                    'Float32': 'FLOAT',
                    'float64': 'FLOAT',
                    'Float64': 'FLOAT',
                    'bool': 'BOOLEAN',
                    'boolean': 'BOOLEAN',
                    'decimal.Decimal': "NUMERIC",
                    'Decimal': "NUMERIC",
                    'datetime64[ns]': 'DATETIME',
                    'datetime': 'DATETIME',
                    'date' : 'DATE',
                    'datetime64[ns, UTC]': 'TIMESTAMP',
                    'Timestamp': 'TIMESTAMP',
                    'date32[day][pyarrow]': 'DATE',
                    'datetime64[us]': 'DATETIME',
                    'geometry' : "GEOGRAPHY",
                    "Polygon" : "GEOGRAPHY",
                    'Timedelta' : "INTERVAL",
                    "timedelta64[ns]" : "INTERVAL"
                }

            if explicit_schema is None:
                explicit_schema = {}

            schema = []

            for column_name, dtype in df.dtypes.items():
                correct_dtype = self._get_dtype(df = df,
                                                column_name=str(column_name))
                bq_spec = explicit_schema.get(column_name, dtype_map.get(correct_dtype, 'STRING'))
                if correct_dtype not in dtype_map.keys() and correct_dtype is not None:
                    logger.warning(f"No mapping from {correct_dtype} to Big Query types for column {column_name}. Current mapping: {dtype_map}")

                if isinstance(bq_spec, tuple):
                    bq_type, bq_mode = bq_spec
                else:
                    bq_type = bq_spec
                    bq_mode = "NULLABLE"

                schema.append(bigquery.SchemaField(str(column_name), bq_type, mode=bq_mode))
                column_to_bq_type[column_name] = bq_type

            df = self._clean_and_prepare_df(df, column_to_bq_type)

        if if_exists in ['append', 'replace']:

            if if_exists == 'append':
                if not table_exists:
                    logger.warning(f"Table {table_id} does not exist. Creating a new table.")
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_APPEND" if table_exists else "WRITE_TRUNCATE",
                    schema=schema,
                    autodetect=autodetect,
                )
            elif if_exists == 'replace':
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_TRUNCATE",
                    schema=schema,
                    autodetect=autodetect,
                )
            try:
                if to_str:
                    df = df.astype(str)
                job = self._bq_client.load_table_from_dataframe(
                    df, table_id, job_config=job_config
                )
                job.result()
                logger.info(f"{len(df)} rader lagret i {table_id}")
            except Exception as e:
                logger.error(
                    f"Error saving to BigQuery: {type(e).__name__}: {e}")
                logger.error(traceback.format_exc())
        elif if_exists == 'merge':

            if not merge_on or not isinstance(merge_on, list):
                raise ValueError(
                    "merge_on parameter must be provided when if_exists is 'merge' and must be a list of column names.")

            duplicates = (df.duplicated(subset=merge_on).sum())
            if duplicates or (duplicates)>0:
                logger.warning(f'There are {(duplicates)} duplicates in the dataframe based on the merge_on columns {merge_on}. They will be removed before merging starts')
                df = df.drop_duplicates(subset=merge_on)


            staging_table_id = f"{table_id}_staging_{uuid.uuid4().hex}"
            logger.info(f"Starting MERGE. Uploading data to staging table: {staging_table_id}")

            try:

                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_TRUNCATE",
                    schema=schema,
                    autodetect=autodetect,
                )
                if to_str:
                    df = df.astype(str)

                job = self._bq_client.load_table_from_dataframe(df, staging_table_id, job_config=job_config)
                job.result()  # Wait for the job to complete
                logger.info(f"Staging table {staging_table_id} created with {len(df)} rows.")

                on_condition = ' AND '.join([f'T.`{key}` = S.`{key}`' for key in merge_on])

                update_cols = [col for col in df.columns if col not in merge_on]
                update_set = ', '.join([f'T.`{col}` = S.`{col}`' for col in update_cols])

                insert_cols = ', '.join([f'`{col}`' for col in df.columns])
                insert_values = ', '.join([f'S.`{col}`' for col in df.columns])

                merge_query = f"""
                                MERGE `{table_id}` AS T
                                USING `{staging_table_id}` AS S
                                ON {on_condition}
                                WHEN MATCHED THEN
                                    UPDATE SET {update_set}
                                WHEN NOT MATCHED THEN
                                    INSERT ({insert_cols})
                                    VALUES ({insert_values})
                                """

                logger.info("Executing MERGE statement...")
                self.exe_query(merge_query)
                logger.info(f"MERGE operation on {table_id} complete.")

            finally:
                logger.info(f"Deleting staging table: {staging_table_id}")
                self._bq_client.delete_table(staging_table_id, not_found_ok=True)
        else:
            raise ValueError(f"Invalid if_exists value: {if_exists}")

    def read_table(self, table_name : str, dataset_name : str) -> pd.DataFrame:
        '''
        Read data from BigQuery.
        
        Args:
            table_name : str - The name of the BigQuery table to read from.
            dataset_name : str - The name of the dataset containing the table.
        Returns:
            pd.DataFrame - A DataFrame containing the data from the specified BigQuery table.
        '''
        query = f"SELECT * FROM `{self.project}.{dataset_name}.{table_name}`"
        df = self._bq_client.query(query).to_arrow().to_pandas()
        #df.replace(['nan', 'None', '', 'null', 'NA', '<NA>', 'NaN', 'NAType'], np.nan, inplace=True)
        logger.info(f"{len(df)} rader lest fra BigQuery")
        return df

    def exe_query(self, query : str) -> bigquery.QueryJob:
        '''
        Execute a BigQuery query
        Args:
            query : str - The SQL query to execute.
        Returns:
            bigquery.QueryJob - The query job object.
        '''
        job = self._bq_client.query(query)
        logger.info(f"Query executed: {query[:100]}... (truncated)")
        return job.result()
    
    def query_to_df(self, query: str) -> pd.DataFrame:
        '''
        Execute a BigQuery query and return the results as a DataFrame.
        Args:
            query : str - The SQL query to execute.
        Returns:
            pd.DataFrame - A DataFrame containing the results of the query.
        '''
        df = self._bq_client.query(query).result().to_dataframe()
        logger.info(f"Query executed and returned {len(df)} rows: {query[:100]}... (truncated)")
        return df