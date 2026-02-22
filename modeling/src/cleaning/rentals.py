import pandas as pd
from ..base import SibrBase
from .transformers import extract_postnummer, extract_datetime
from .feature_builder import (
    mk_num, mk_cat, mk_fractions, mk_bool_features,
    split_date, process_bool, transform_nan, rm_empty_features, fill_na,
    add_missing_features, ensure_num_types,
)


class RentalsCleaner(SibrBase):
    def __init__(self, logger=None, df=None):
        super().__init__(dataset='rentals', logger=logger)
        self.logger.info('RentalsCleaner initialized.')
        self.df = df
        self.geo = None

    def clean(self) -> pd.DataFrame:
        df = transform_nan(self.df)
        df = rm_empty_features(df)

        int_cols = [
            'monthly_rent', 'deposit', 'bedrooms', 'floor',
            'primary_area', 'usable_area', 'internal_area', 'gross_area', 'external_area'
        ]
        df = mk_num(df, int_cols, type='int')

        df.loc[:, 'bedrooms'] = df['bedrooms'].fillna(0)
        df.loc[:, 'floor'] = df['floor'].fillna(0)

        if 'primary_area' in df.columns and 'usable_area' in df.columns:
            df.loc[:, 'primary_area'] = df['primary_area'].fillna(df['usable_area'])
        df.loc[:, 'primary_area'] = df['primary_area'].fillna(0)

        df = mk_fractions(df, new_feat_name='rent_pr_sqm', numerator='monthly_rent', denominator='primary_area')
        df = mk_fractions(df, new_feat_name='price_pr_bedroom', numerator='monthly_rent', denominator='bedrooms')
        df = mk_fractions(df, new_feat_name='sqm_pr_bedroom', numerator='primary_area', denominator='bedrooms')
        df['rent_pr_sqm'] = df['rent_pr_sqm'] * 12
        df['price_pr_bedroom'] = df['price_pr_bedroom'] * 12

        df = df[
            (df['monthly_rent'] > 1000) & (df['monthly_rent'] < 300000)
            & ((df['primary_area'] >= 0) & (df['primary_area'] < 1000))
            & ((df['bedrooms'] >= 0) & (df['bedrooms'] < 10))
            & ((df['floor'] >= 0) & (df['floor'] < 100))
            ]
        self.logger.debug(f'Length: {len(df)} | after filter price and usable_area')

        df['scrape_date'] = pd.to_datetime(df['scrape_date'], errors='coerce', utc=True)
        df['clean_date'] = pd.Timestamp.now()
        self.logger.debug(f'Length: {len(df)} | after datetime conversion')

        df['postal_code'] = df['address'].apply(extract_postnummer)
        df = pd.merge(df, self.geo[['postal_code', 'municipality', 'county', 'region']], how='left',
                      on='postal_code')
        self.logger.debug(f'Length: {len(df)} | after geo')

        df['includes'] = df['includes'].apply(lambda x: x.replace("inkluderer", "") if isinstance(x, str) else x)

        df.loc[:, 'property_type'] = df['property_type'].str.replace(r'^boligtype', '', case=False, regex=True)
        df['property_type'] = df['property_type'].apply(lambda x: x.replace('/', "_") if isinstance(x, str) else x)
        df.loc[:, 'dealer'] = df['dealer'].fillna('private')

        def clean_includes(text):
            if not isinstance(text, str):
                return text
            text = text.lower().strip()
            replacements = [
                ("inkludererbredbånd", "internett"),
                ("inkludererinternett", "internett"),
                ("inkludererstrøm", "strøm"),
                ("inkluderervarmtvann", "varmtvann"),
                ("inkluderer", "")
            ]
            for old, new in replacements:
                text = text.replace(old, new)
            return text

        df['includes'] = df['includes'].apply(clean_includes)
        bool_dict = {
            'eq_power': ['strøm', 'strøm og internett'],
            'eq_internet': ['internett', 'bredbånd', 'fiber', 'strøm og internett', 'wifi',
                            'grunnpakke internett og grunnpakke tv er inkludert i leien.', 'internet',
                            'tv og internett'],
            'eq_tv': ['tv', 'kabel-tv', 'kabel-/digital-tv', 'kabel tv', 'kabeltv',
                      'grunnpakke internett og grunnpakke tv er inkludert i leien.', 'tv og internett'],
            'eq_hot_water': ['varmtvann', 'varmt vann'],
            'eq_water': ['vann'],
            'eq_heating': ['oppvarming', 'oppvarming fra vannbåren varme'],
            'eq_parking': ['parkering', 'parkeringsplass'],
            'eq_household_appliances': ['hvitevarer', 'vaskemaskin', 'tørketrommel', 'oppvaskmaskin'],
            'eq_furniture': ['møbler', 'møblert'],
        }
        df = mk_bool_features(df=df, equipment_features=bool_dict, source_col='includes')
        self.logger.debug(f'Length: {len(df)} | after bool features')

        df.loc[:, "last_updated"] = df["last_updated"].apply(
            lambda x: extract_datetime(x) if isinstance(x, str) else x)
        df["last_updated"] = pd.to_datetime(df["last_updated"])

        extra_cols = ['email', 'web', 'energy_rating']
        add_missing_features(df, extra_cols)

        self.df = df
        return df

    def pre_process(self, df=None, save_to_bq=True):
        if df is not None:
            self.df = df
        df = self.df.dropna(subset='item_id')
        df.drop_duplicates(subset=['item_id'], inplace=True)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on item_id')
        df.dropna(subset=['monthly_rent', 'primary_area'], inplace=True)

        drop = [
            'address', 'description', 'contact_person', 'phone', 'url', 'country', 'title',
            'facilities', 'deposit', 'includes', 'web', 'email',
            'rn', 'FIRST', 'LAST', 'postal_code', 'municipality', 'county', 'region', 'salgstid',
            'price_pr_bedroom', 'rent_pr_sqm', 'clean_date', 'energy_rating', 'internal_area',
            'gross_area', 'usable_area'
        ]
        df.drop(columns=drop, inplace=True, errors='ignore')

        df = df[
            (df['monthly_rent'] > 1000) & (df['monthly_rent'] < 50000)
            & ((df['primary_area'] > 0) & (df['primary_area'] < 200))
            ]
        df = rm_empty_features(df)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on price, usable_area and bedrooms')

        prop_type = ['Enebolig', 'Leilighet', 'Rom i bofellesskap', 'Tomannsbolig',
                     'Hybel', 'Andre', 'Rekkehus']
        df = mk_cat(df, 'property_type', prop_type)
        self.logger.debug(f'Unique property types: {df["property_type"].unique()}')
        df['dealer'] = df['dealer'].apply(lambda x: False if x.lower() == 'private' else True)
        self.logger.debug(f'Length of df: {len(df)} | after mapping categories')

        df = process_bool(df)
        df = split_date(df, date_col='scrape_date')
        df = split_date(df, date_col='last_updated')
        df['pre_processed_date'] = pd.Timestamp.now()
        self.logger.debug(f'Length of df: {len(df)} | after date columns')
        df = ensure_num_types(df, num_types=['int', 'float'])

        df_r = df[df['property_type'] != 'rom i bofellesskap']
        df_k = df[df['property_type'] == 'rom i bofellesskap']

        def rm_rental_outliers(df: pd.DataFrame) -> pd.DataFrame:
            if 'bedrooms' in df.columns and 'monthly_rent' in df.columns:
                mask_to_drop = (df['bedrooms'] == 0) & (df['monthly_rent'] > 20000)
                df = df[~mask_to_drop]
            return df

        df_r = rm_rental_outliers(df_r)

        prop_type_r = ['Enebolig', 'Leilighet', 'Tomannsbolig', 'Andre', 'Rekkehus', 'Hybel']
        df_r = mk_cat(df_r, 'property_type', prop_type_r)
        df_r = pd.get_dummies(df_r, columns=['property_type'], drop_first=True)
        self.logger.debug(f'Length of df_r: {len(df_r)} | Before saving to BQ. Replace is {self.replace}')
        if "pre_processed_date" not in df_r.columns:
            df_r['pre_processed_date'] = pd.Timestamp.now()
        if save_to_bq:
            self.save_data(df=df_r, table_name='rentals')

        df_k = df_k.drop(columns=['dealer_True', 'property_type', 'bedrooms', 'sqm_pr_bedroom', 'primary_area'],
                         errors='ignore')
        self.logger.debug(f'Length of df_k: {len(df_k)} | Before saving to BQ. Replace is {self.replace}')
        if save_to_bq:
            self.save_data(df=df_k, table_name='rentals_co-living')

        return df_r, df_k

    def run(self, task: str, df=None, save_to_bq: bool = True, replace: bool = False):
        if task not in ['clean', 'pre_processed']:
            raise ValueError(f'Unsupported task: {task}. Supported tasks are "clean" and "pre_processed".')
        self.logger.info(
            f'Running task: {task} for dataset: {self.dataset} with replace={replace} and save_to_bq={save_to_bq}')
        try:
            if replace:
                self.replace = replace
            self.task_name = task
            if self.task_name == 'clean':
                if df is None:
                    self.read_in_data()
                else:
                    self.df = df
                cleaned_df = self.clean()
                if save_to_bq:
                    self.save_data(df=cleaned_df, table_name=self.dataset)
                return cleaned_df
            elif self.task_name == 'pre_processed':
                if df is None:
                    self.read_in_data()
                else:
                    self.df = df
                return self.pre_process(save_to_bq=save_to_bq)
        finally:
            self.logger.shutdown()
