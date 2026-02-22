import ast
import pandas as pd
from ..base import SibrBase
from .transformers import extract_int, extract_postnummer, extract_datetime
from .feature_builder import (
    mk_num, mk_cat, mk_fractions, mk_bool_features, mk_bool_description,
    split_date, process_bool, transform_nan, rm_empty_features, fill_na,
    add_missing_features, ensure_num_types,
)


class NewHomesCleaner(SibrBase):
    def __init__(self, logger=None, df=None):
        super().__init__(dataset='new_homes', logger=logger)
        self.logger.info('NewHomesCleaner initialized.')
        self.df = df
        self.geo = None

    def clean(self) -> pd.DataFrame:
        """Clean new_homes data using the same logic as HomesCleaner."""
        df = transform_nan(self.df)
        df = rm_empty_features(df)
        self.logger.debug(f'Length: {len(df)} | after merge with sales time')

        int_cols = [
            'price', 'balcony', 'total_price', 'bedrooms', 'rooms', 'build_year',
            'usable_area', 'internal_area', 'external_area', 'plot_size', 'fees',
            'joint_debt', 'monthly_common_cost', 'collective_assets', 'tax_value', 'floor'
        ]
        df = mk_num(df, int_cols, type='int')

        cadastre_fields = ["cadastral_num", "unit_num", "section_num", "coop_unit_num",
                           "municipality_num", "coop_org_num", "leasehold_num"]

        def fix_cadastre(x):
            val = ast.literal_eval(x)
            if isinstance(val, list):
                for e in val:
                    res = extract_int(e)
                    if res is not None:
                        return res
            else:
                self.logger.warning(f'Unexpected dtype {type(val)} | {val} for cadastre field.')
                return val

        for field in cadastre_fields:
            df.loc[:, field] = df[field].apply(lambda x: fix_cadastre(x) if isinstance(x, str) else x)
            df[field] = pd.to_numeric(df[field], errors='coerce')

        df['total_price'] = df['total_price'].astype('float')
        df['total_price'] = df['total_price'].fillna(df['price'].astype('float') * 1.025)
        df['total_price'] = df['total_price'].round().astype('Int64')
        df.loc[:, 'bedrooms'] = df['bedrooms'].fillna(0)
        df['bedrooms'] = df['bedrooms'].fillna(0)
        df['external_area'] = df['external_area'].fillna(0)
        df['internal_area'] = df['internal_area'].fillna(df['usable_area'] - df['external_area'])
        df['usable_area'] = df['usable_area'].fillna(df['internal_area'])
        df['internal_area'] = df['internal_area'].fillna(df['usable_area'])
        df['floor'] = df['floor'].fillna(0)

        df = mk_fractions(df, new_feat_name='price_pr_sqm', numerator='price', denominator='usable_area')
        df = mk_fractions(df, new_feat_name='price_pr_i_sqm', numerator='price', denominator='internal_area')
        df = mk_fractions(df, new_feat_name='price_pr_bedroom', numerator='price', denominator='bedrooms')
        df = mk_fractions(df, new_feat_name='sqm_pr_bedroom', numerator='usable_area', denominator='bedrooms')
        df = mk_fractions(df, new_feat_name='monthly_common_cost_pr_sqm', numerator='monthly_common_cost',
                          denominator='usable_area')
        df['sqm_pr_bedroom'] = df['sqm_pr_bedroom'].fillna(df['usable_area'])

        df.drop('primary_area', axis=1, inplace=True, errors='ignore')

        df = df[
            (df['price'] > 200000) & (df['price'] < 30000000)
            & ((df['usable_area'] > 0) & (df['usable_area'] < 1500))
            & ((df['internal_area'] > 0) & (df['internal_area'] < 1500))
            & ((df['bedrooms'] >= 0) & (df['bedrooms'] < 10))
            & ((df['floor'] >= 0) & (df['floor'] < 100))
            & ((df['total_price'] >= 0) & (df['total_price'] < 35000000))
            ]
        self.logger.debug(f'Length: {len(df)} | after filter price and usable_area')

        df['scrape_date'] = pd.to_datetime(df['scrape_date'], errors='coerce', utc=True)
        df['clean_date'] = pd.Timestamp.now()

        df['postal_code'] = df['address'].apply(extract_postnummer)
        df = pd.merge(df, self.geo[['postal_code', 'municipality', 'county', 'region']], how='left',
                      on='postal_code')

        df['ownership_type'] = df['ownership_type'].str.replace(r'^eieform', '', case=False, regex=True).str.strip()
        df['ownership_type'] = df['ownership_type'].apply(
            lambda x: x.replace('(Selveier)', "").strip() if isinstance(x, str) else x)
        cond = (df["ownership_type"].isna()) & (
                (df["property_type"].str.lower() != "leilighet") | (df["section_num"].notna()))
        df.loc[cond, "ownership_type"] = "Eier"

        df['property_type'] = df['property_type'].str.replace(r'^boligtype', '', case=False, regex=True)
        df['property_type'] = df['property_type'].apply(
            lambda x: x.replace('/', "_") if isinstance(x, str) else x).str.strip()
        df['dealer'] = df['dealer'].fillna('private').str.strip()

        equipment_features = {
            'eq_parking': ["parkering", "p-plass", "parkeringsplass", "garasje/p-plass"],
            "eq_lift": ["heis", "løfteplattform"],
            "eq_fireplace": ['peis', "peis/ildsted"],
            "eq_charging_possibility": ["lademulighet"],
            "eq_aircondition": ["aircondition"],
            "eq_garden": ["hage"],
            "eq_pool": ["badebasseng", "basseng", "boblebad", "jacuzzi"]
        }
        df = mk_bool_features(df=df, equipment_features=equipment_features, source_col="facilities")

        df = mk_bool_description(df=df, col_name="eq_parking_tmp",
                                 keys=["parkering", "p-plass", "parkeringsplass", "garasje/p-plass"],
                                 source_cols=["description", "title"])
        df = mk_bool_description(df=df, col_name="eq_lift_tmp",
                                 keys=["heis", "løfteplattform"],
                                 source_cols=["description", "title"])
        df = mk_bool_description(df=df, col_name="eq_pool_tmp",
                                 keys=["badebasseng", "basseng", "boblebad", "jacuzzi"],
                                 source_cols=["description", "title"])

        df['eq_parking'] = df.apply(lambda row: True if row['eq_parking_tmp'] or row['eq_parking'] else False,
                                    axis=1)
        df['eq_lift'] = df.apply(lambda row: True if row['eq_lift_tmp'] or row['eq_lift'] else False, axis=1)
        df['eq_pool'] = df.apply(lambda row: True if row['eq_pool_tmp'] or row['eq_pool'] else False, axis=1)
        df.drop(columns=['eq_parking_tmp', 'eq_lift_tmp', "eq_pool_tmp"], inplace=True, errors="ignore")

        keys_fixer_upper = [
            'oppussingsobjekt', 'oppussingsbehov', 'oppussingsklar', 'renoveringsobjekt', 'oppgraderingsobjekt',
            'renoveringsbehov', 'moderniseringsbehov', 'moderniseringsobjekt', 'oppgraderingsbehov',
            'rehabilitering/oppussing', 'rehabilitering', 'oppussing', 'oppgradering og vedlikehold',
            'rehabiliteringsbehov'
        ]
        keys_renovated = ['nylig oppusset', 'nyoppusset', 'totalrenovert', 'pusset opp', 'renovert',
                          'totalrehabilitert', "oppusset"]
        df = mk_bool_description(df=df, col_name='fixer_upper', keys=keys_fixer_upper,
                                 source_cols=['description', 'title'])
        df = mk_bool_description(df=df, col_name="renovated", keys=keys_renovated,
                                 source_cols=['description', 'title'])
        df = mk_bool_description(df=df, col_name='eq_rental_unit',
                                 keys=["utleiedel", "utleiebolig", "utleieenhet", "utleie del", "utleie bolig",
                                       "utleie enhet", "anneks"],
                                 source_cols=['description', 'title'])
        df = mk_bool_description(df=df, col_name="eq_west_facing",
                                 keys=["vestvendt terrasse", "vestvendt", "vestvendt balkong"],
                                 source_cols=["description", "title"])
        df = mk_bool_description(df=df, col_name="eq_sauna",
                                 keys=["badstue", "sauna"],
                                 source_cols=["description", "title"])

        if 'sold' in df.columns:
            df['sold'] = df['sold'].str.lower().str.strip()
            df['sold'] = df['sold'].apply(lambda x: True if pd.notna(x) and x == 'solgt' else False)
            df['sold'] = df['sold'].fillna(False)
            df['sold'] = df['sold'].astype('boolean')

        df.loc[:, "last_updated"] = df["last_updated"].apply(
            lambda x: extract_datetime(x) if isinstance(x, str) else x)
        df["last_updated"] = pd.to_datetime(df["last_updated"])

        extra_cols = ['email', 'web']
        df = add_missing_features(df, extra_cols)
        df = ensure_num_types(df, num_types=['int', 'float'])

        self.logger.debug(f'Length: {len(df)} | before saving to BQ. Replace {self.replace}')
        self.df = df
        return df

    def pre_process(self, df=None, save_to_bq=True):
        if df is not None:
            self.df = df
        df = self.df.dropna(subset='item_id')
        df.drop_duplicates(subset=['item_id'], inplace=True)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on item_id')
        df.dropna(subset=['price', 'usable_area', 'bedrooms'], inplace=True)

        drop = [
            'district', 'address', 'title', 'sold',
            'description', 'email', 'contact_person', 'phone', 'url', 'new', 'country',
            'facilities', 'energy_rating',
            'rn', 'FIRST', 'LAST', 'postal_code', 'municipality', 'county', 'region', 'salgstid',
            'tax_value', 'total_price', 'price_pr_bedroom', 'price_pr_sqm', 'web',
            'cadastral_num', 'unit_num', 'section_num', 'clean_date', 'price_pr_i_sqm',
            'fees', "coop_name", "apartment_num"
        ]
        df.drop(columns=drop, inplace=True, errors='ignore')
        df = rm_empty_features(df)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on price, usable_area and bedrooms')

        df = df[df['property_type'] != 'Garasje/Parkering']
        df['dealer'] = df['dealer'].apply(lambda x: False if x.lower() == 'private' else True)
        df = process_bool(df)

        prop_type = ['Leilighet', 'Enebolig', 'Tomannsbolig', 'Rekkehus',
                     'Gårdsbruk_Småbruk', 'Andre', 'Bygård_Flermannsbolig']
        own_type = ['Eier', 'Andel', 'Aksje', 'Annet', 'Obligasjon']
        df = mk_cat(df, 'property_type', prop_type)
        df = mk_cat(df, 'ownership_type', own_type)
        df = pd.get_dummies(df, columns=['ownership_type'], drop_first=True)

        df = split_date(df, date_col='scrape_date')
        df = split_date(df, date_col='last_updated')
        df['pre_processed_date'] = pd.Timestamp.now()

        cols_to_convert = [col for col in df.columns if col != 'sqm_pr_bedroom']
        df[cols_to_convert] = ensure_num_types(df[cols_to_convert], num_types=['int'])

        df_a = df[df['property_type'] == 'leilighet']
        df_h = df[df['property_type'] != 'leilighet']
        rental_cols = ['property_type', 'bedrooms', 'floor', 'usable_area', 'day', 'month', 'year',
                       'sqm_pr_bedroom', "item_id"]
        df_r = df[rental_cols]

        df_a = pd.get_dummies(df_a, columns=['property_type'], drop_first=True)
        df_a.loc[:, 'balcony'] = df_a['balcony'].fillna(0)
        df_a.loc[:, 'floor'] = df_a['floor'].fillna(0)
        df_a.loc[:, 'rooms'] = df_a['rooms'].fillna(df_a['bedrooms'] + 1)
        df_a.loc[:, 'external_area'] = df_a['external_area'].fillna(0)
        df_a.loc[:, 'monthly_common_cost'] = df_a['monthly_common_cost'].fillna(0)
        self.logger.debug(f'Length of df_a: {len(df_a)} | before saving to BQ.')
        if save_to_bq:
            self.save_data(df_a, 'new_homes_apartments')

        drop_h = ['collective_assets', 'joint_debt', 'balcony', 'floor', 'monthly_common_cost', 'rooms',
                  'external_area']
        df_h.drop(columns=drop_h, inplace=True, errors='ignore')
        df_h = pd.get_dummies(df_h, columns=['property_type'], drop_first=True)
        self.logger.debug(f'Length of df_h: {len(df_h)} | before saving to BQ.')
        if save_to_bq:
            self.save_data(df_h, 'new_homes_houses', explicit_schema={"sqm_pr_bedroom": "FLOAT"})

        df_r.rename({'usable_area': 'primary_area'}, axis=1, inplace=True)
        order = ["item_id", 'bedrooms', 'floor', 'primary_area', 'sqm_pr_bedroom',
                 'day', 'month', 'year', 'property_type']
        df_r = df_r[order]
        prop_type_r = ['Enebolig', 'Leilighet', 'Tomannsbolig', 'Andre', 'Rekkehus']
        df_r = mk_cat(df_r, 'property_type', prop_type_r)
        df_r = pd.get_dummies(df_r, columns=['property_type'], drop_first=True)
        self.logger.debug(f'Length of df_r: {len(df_r)} | before saving to BQ.')
        if save_to_bq:
            self.save_data(df_r, 'new_homes_rentals')

        return df_a, df_h, df_r

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
                    self.save_data(df=cleaned_df, table_name=self.dataset,
                                   explicit_schema={"coop_unit_num": "INTEGER", "coop_org_num": "INTEGER"})
                return cleaned_df
            elif self.task_name == 'pre_processed':
                if df is None:
                    self.read_in_data()
                else:
                    self.df = df
                return self.pre_process(save_to_bq=save_to_bq)
        finally:
            self.logger.shutdown()
