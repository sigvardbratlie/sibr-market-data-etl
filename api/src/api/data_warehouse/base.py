from abc import ABC, abstractmethod
from typing import Literal
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataBase(ABC):
    
    def _clean_and_prepare_df(self, df: pd.DataFrame, schema_mapping: dict) -> pd.DataFrame:
        """Renser og klargjør DataFrame i henhold til BigQuery-skjemaet."""
        df_copy = df.copy()
        for column, dtype in schema_mapping.items():
            if column not in df_copy.columns:
                continue

            # Tving kolonner til riktig type og erstatt feil med NaN/NaT
            if dtype in ['INTEGER', 'FLOAT']:
                df_copy[column] = pd.to_numeric(df_copy[column], errors='coerce')
                # For Integer, må vi bruke Pandas' nullable integer type for å beholde NaN
                if dtype == 'INTEGER':
                    df_copy[column] = df_copy[column].astype('Int64')  # Nullable Integer
            elif dtype in ['DATETIME', 'TIMESTAMP', 'DATE']:
                df_copy[column] = pd.to_datetime(df_copy[column], errors='coerce', utc=True)
                # Konverter til None der det er NaT (Not a Time), som BigQuery-klienten håndterer
                df_copy[column] = df_copy[column].replace({pd.NaT: None})

        logger.info("DataFrame cleaned and prepared for BigQuery upload.")
        return df_copy

    def _get_dtype(self, df: pd.DataFrame, column_name: str):
        """
        Finds the Python data type of the first non-null element in a DataFrame column.

        :param df: The DataFrame.
        :param column_name: The name of the column to check.
        :return: The name of the data type (e.g., 'str', 'int'), or None if the column is empty or all-null.
        """
        # Lag en ny serie uten null-verdier (NaN, None, etc.)
        non_null_series = df[column_name].dropna()

        # Hvis serien er tom etter fjerning av null-verdier, returner None
        if non_null_series.empty:
            logger.warning(f"Column '{column_name}' contains only null values or is empty.")
            return None

        # Hent det aller første elementet som ikke er null og returner typenavnet
        first_valid_element = non_null_series.iloc[0]
        return type(first_valid_element).__name__

    
    @abstractmethod
    def save_table(self, df : pd.DataFrame,
              table_name : str,
              dataset_name : str,
              if_exists: Literal['append', 'replace', 'merge'] = 'append',
              to_str=False,
              merge_on=None,
              autodetect : bool = False,
              dtype_map : dict = None,
              explicit_schema : dict = None) -> None:
        pass

    @abstractmethod
    def read_table(self, table_name : str, dataset_name : str) -> pd.DataFrame:
        pass

    @abstractmethod
    def exe_query(self, *args, **kwargs):
        pass

    @abstractmethod
    def query_to_df(self, query: str, params = None) -> pd.DataFrame:
        pass
