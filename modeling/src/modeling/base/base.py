import os
import json
import joblib
from google.cloud import storage
from modeling.data_warehouse import CustomBigQuery, load_google_credentials

import logging
logger = logging.getLogger(__name__)

class SibrBase:
    def __init__(self, dataset):
        self._dataset = dataset
        self._task_name = None
        self._replace = False
        self._bucket_name = 'sibr-market'
        self._project_id = 'sibr-market'
        self.bq = None
        self._bucket = None
        self.df = None
        self.geo = None
        self.setup()

    @property
    def dataset(self):
        return self._dataset

    @property
    def replace(self):
        return self._replace

    @replace.setter
    def replace(self, value):
        if isinstance(value, bool):
            self._replace = value
        else:
            raise ValueError("Replace must be a boolean value.")

    @property
    def task_name(self):
        return self._task_name

    @task_name.setter
    def task_name(self, value):
        if value in ['admin', 'clean', 'pre_processed', 'raw', 'predictions', 'train']:
            self._task_name = value
        else:
            raise ValueError("Task name must be one of: 'admin', 'clean', 'pre_processed', 'raw', 'predictions'.")

    def setup(self):
        self.bq = CustomBigQuery(credentials = load_google_credentials(), dataset=self._dataset)
        gcs = storage.Client(credentials=load_google_credentials())
        self._bucket = gcs.bucket(self._bucket_name)
        logger.debug(f'Dataset: {self.dataset} | | Replace: {self.replace}')

    def gcs_download(self, blob_name: str, local_path: str = None, read_in_file: bool = False):
        """Download a blob from GCS. If read_in_file=True, returns the loaded object (pkl or json)."""
        blob = self._bucket.blob(blob_name)
        if read_in_file:
            tmp_path = f'/tmp/{os.path.basename(blob_name)}'
            blob.download_to_filename(tmp_path)
            try:
                ext = blob_name.rsplit('.', 1)[-1].lower()
                if ext == 'pkl':
                    return joblib.load(tmp_path)
                elif ext == 'json':
                    with open(tmp_path) as f:
                        return json.load(f)
                else:
                    with open(tmp_path) as f:
                        return f.read()
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        else:
            blob.download_to_filename(local_path)

    def gcs_upload(self, local_path: str, blob_name: str):
        """Upload a local file to GCS."""
        self._bucket.blob(blob_name).upload_from_filename(local_path)

    def save_data(self, df, table_name, explicit_schema=None):
        if self.task_name not in ['admin', 'clean', 'pre_processed', 'raw', 'predictions']:
            raise ValueError(
                f'Task name "{self.task_name}" is not allowed for saving data. Must be one of: "admin", "clean", "pre_processed", "raw", "predictions".')
        if self.replace:
            self.bq.save_table(df,
                          table_name=table_name,
                          dataset_name=self.task_name,
                          if_exists='replace',
                          explicit_schema=explicit_schema)
        else:
            self.bq.save_table(df,
                          table_name=table_name,
                          dataset_name=self.task_name,
                          if_exists='merge',
                          merge_on=['item_id'],
                          explicit_schema=explicit_schema)

    def read_in_data(self):
        if self.task_name == 'clean':
            logger.info(f'📥 Reading raw data for: {self.dataset}')
            self.df = self.bq.read_raw(replace=self.replace)
            self.geo = self.bq.read_geonorge()
            if self.df is None or self.df.empty:
                logger.error(f'❌ No data found for task "{self.task_name}" — cannot continue.')
                raise ValueError("No data found in BigQuery for the 'clean' task.")
        elif self.task_name == 'pre_processed':
            logger.info(f'📥 Reading clean data for: {self.dataset}')
            self.df = self.bq.read_clean(replace=self.replace)
        else:
            raise ValueError(
                f'Task name "{self.task_name}" is not allowed for reading data. Must be "clean" or "pre_processed".')

    def mk_num(self, df, int_cols, type='int'):
        from ..cleaning.feature_builder import mk_num
        return mk_num(df, int_cols, type)
