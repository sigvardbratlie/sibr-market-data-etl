import ast
import pandas as pd
from ..base import SibrBase
from .transformers import extract_postnummer, extract_datetime
from .feature_builder import (
    mk_num, mk_cat, mk_fractions, mk_bool_features, mk_bool_description,
    split_date, process_bool, transform_nan, rm_empty_features, fill_na,
    add_missing_features, ensure_num_types, rm_nan_cols,
)


class CarsCleaner(SibrBase):
    def __init__(self, logger=None, df=None):
        super().__init__(dataset='cars', logger=logger)
        self.logger.info('CarsCleaner initialized.')
        self.df = df
        self.geo = None

    def clean(self) -> pd.DataFrame:
        df = transform_nan(self.df)
        df = rm_empty_features(df)
        self.logger.debug(f'Length: {len(df)} | after merge with sales time')

        int_cols = [
            'model_year', 'mileage', 'transfer_fee', 'price_excl_transfer', 'power',
            'co2', 'weight', 'seats', 'prev_owners', 'doors', 'trailer_weight',
            'last_eu', 'next_eu', 'range', 'battery', 'liens', 'total_price', 'rn',
            'engine_volume', 'cargo_space'
        ]
        df = mk_num(df, int_cols, type='int')

        if "transfer_fee" in df.columns:
            df['transfer_fee'] = df['transfer_fee'].fillna(0)

        df = df[
            (df['total_price'] > 10000) & (df['total_price'] < 3000000)
            & ((df['mileage'] >= 0) & (df['mileage'] < 1000000))
            & ((df['weight'] >= 0) & (df['weight'] < 10000))
            & ((df['seats'] >= 0) & (df['seats'] < 10))
            & ((df['doors'] >= 0) & (df['doors'] < 10))
            & ((df['model_year'] >= 1900) & (df['model_year'] < 2030))
            & ((df['power'] >= 0) & (df['power'] < 5000))
            ]
        self.logger.debug(f'Length: {len(df)} | after filter price and usable_area')

        df = mk_fractions(df, "price_pr_km", "total_price", "mileage")

        df['scrape_date'] = pd.to_datetime(df['scrape_date'], errors='coerce', utc=True)
        df['clean_date'] = pd.Timestamp.now()
        self.logger.debug(f'Length: {len(df)} | after datetime conversion')

        df['postal_code'] = df['address'].apply(extract_postnummer)
        df = pd.merge(df, self.geo[['postal_code', 'municipality', 'county', 'region']], how='left',
                      on='postal_code')
        self.logger.debug(f'Length: {len(df)} | after geo')

        fuel_mapping = {
            'diesel': 'diesel', 'bensin': 'bensin', 'el': 'el', 'elektrisitet': 'el',
            'el + bensin': 'el + bensin', 'hybrid bensin': 'el + bensin',
            'plug-in bensin': 'el + bensin', 'el + diesel': 'el + diesel',
            'hybrid diesel': 'el + diesel', 'plug-in diesel': 'el + diesel',
            'hydrogen': 'hydrogen'
        }
        brand_mapping = {
            'tesla motors': 'tesla', 'bmw i': 'bmw', 'alfa': 'alfa romeo',
            'jaguar land rover limited': 'land rover',
            'automobili lamborghini s.p.a.': 'lamborghini',
            'land': 'land rover', 'rover': 'land rover', 'range rover': 'land rover',
            'mercedes sprinter / kegger': 'mercedes-benz', 'mercedes-amg': 'mercedes-benz',
            'ford-cng-technik': 'ford', 'daimler': 'mercedes-benz',
            'kg mobility': 'kgm', 'mitsubishi fuso': 'mitsubishi',
            'jaguar cars limited': 'jaguar'
        }
        for col in ['fuel', 'brand']:
            df.loc[:, col] = df[col].str.lower()
            if col == 'fuel':
                df.loc[:, col] = df[col].map(fuel_mapping).fillna('annet')
            elif col == 'brand':
                df.loc[:, col] = df[col].replace(brand_mapping)
        self.logger.debug(f'Length: {len(df)} | after category mapping')

        df = fill_na(df, feature='gearbox', fill_value='Automat')
        df = fill_na(df, feature='body_type', fill_value='SUV/Offroad')
        df = fill_na(df, feature='sales_type', fill_value='Bruktbil til salgs')
        df = fill_na(df, feature='dealer', fill_value='private')
        df = fill_na(df, feature='known_issues', fill_value='False')
        df = fill_na(df, feature='major_repairs', fill_value='False')
        df = fill_na(df, feature='engine_tuned', fill_value='False')
        df = fill_na(df, feature='liens', fill_value=False)
        df.loc[:, 'liens'] = df['liens'].astype('object').astype(str)
        self.logger.debug(f'Length: {len(df)} | after fill_na')

        keys_carparts = [
            'delebil', 'rep objekt', 'reparasjonsobjekt', 'repobjekt', 'restaureringsobjekt',
            'reparasjons objekt', 'motorhavari', 'motor havari', 'motorhavart',
            'motor starter ikke', 'motoren starter ikke', 'motorhavarert', 'motor havarert',
            'motorfeil', 'motor feil', 'chippet', 'defekt motor', 'rådebank', "rep-objekt"
        ]
        keys_regreim = [
            'regreim', 'reg.reim', 'reg reim', 'reg.reim byttet', 'registerreim',
            'registerreim byttet',
        ]
        df = mk_bool_description(df, 'car_for_parts', keys_carparts, source_cols=['description'])
        df = mk_bool_description(df, 'timing_belt', keys_regreim, source_cols=['description'])

        equipment_features = {
            'eq_cruise_control': ['cruisekontroll', 'cruisekontroll adaptiv', 'cruise controll adaptive',
                                  'adaptiv cruisekontroll', 'adaptive cruise control', 'adaptiv cruise control'],
            'eq_parking_sensor_behind': ['parkeringsensor bak', 'avstandsføler bak', 'parkeringssensorer: bak',
                                         'parkeringssensor bak'],
            'eq_parking_sensor_front': ['parkeringsensor foran', 'avstandsføler foran', 'parkeringssensorer: foran',
                                        'parkeringssensor foran'],
            'eq_parking_assistant': ['parkeringsassistent'],
            'eq_driving_computer': ['kjørecomputer'],
            'eq_rear_view_camera': ['ryggekamera'],
            'eq_bluetooth': ['bluetooth', 'bluetooth: mobil', 'bluetooth handsfree', 'bluetooth®-forbindelse',
                             'bluetooth telefon og streaming'],
            'eq_tow_hitch': ['hengerfeste', 'henger feste', 'avtagbart hengerfeste', 'tilhengerfeste'],
            'eq_360_camera': ['360 kamera', '360-kamera', '360 graders overvåkning'],
            'eq_internet': ['internett', 'internet', 'internettilkobling'],
            'eq_app': ['app-tilkobling', 'app'],
            'eq_skin_interior': ['skinninteriør', 'skinn seter', 'skinnseter', 'skinn', 'seter i helskinn'],
            'eq_air_conditioning': ['klimaanlegg', 'aircondition', 'air condition', 'klimaanlegg bak',
                                    'klimaanlegg foran', 'automatisk klimaanlegg', 'ventilasjon'],
            'eq_dab': ['dab-radio', 'dab radio', 'dab'],
            'eq_apple_carplay': ['apple carplay'],
            'eq_TCS': ['antispinn'],
            'eq_ESC': ['antiskrens'],
            'eq_sunroof': ['soltak', 'takluke', 'soltak/glasstak', 'panorama glasstak'],
            'eq_traffic_sign_recognition': ['trafikkskiltgjenkjenning', 'veiskiltinformasjon'],
            'eq_led_lights': ['led hovedlys', 'ledlys', 'led lys', 'lys led kjørelys'],
            'eq_xenon_lights': ['xenonlys', 'bi-xenon', 'xenon'],
            'eq_alarm': ['alarm', 'tyverialarm'],
            'eq_high_beam_assistant': ['fjernlysassistent'],
            'eq_keyless_start': ['nøkkelløs start', 'nøkkelfri lås/start'],
            'eq_keyless_go': ['nøkkelløs adgang', 'keyless go', 'nøkkelløs åpning'],
            'eq_abs': ['abs-bremser', 'abs'],
            'eq_isofix': ['isofix', 'isofix barnesetefesting', 'isofix: bak', 'isofix-monteringspunkter'],
            'eq_roof_railing': ['takrails', 'takstativ', 'takreling'],
            'eq_roof_box': ['takboks'],
            'eq_pollen_filter': ['pollenfilter', 'pollen filter'],
            'eq_airbag': ['airbags', 'kollisjonspute', 'kollisjonsputer', 'airbag foran side', 'airbag bak side'],
            'eq_power_steering': ['servostyring'],
            'eq_metallic_paint': ['metallisk lakk', 'metallakk'],
            'eq_handsfree': ['handsfree', 'handsfree opplegg', 'bluetooth handsfree'],
            'eq_alloy_wheels_summer': ['lettmet. felg sommer'],
            'eq_alloy_wheels_winter': ['lettmet. felg vinter'],
            'eq_navigation': ['navigasjonssystem'],
            'eq_charging_cable': ['laderkabel', 'lader kabel', 'ladekabel', 'ladeledning'],
            'eq_central_locking': ['sentrallås', 'fjernstyrt sentrallås'],
            'eq_rain_sensor': ['regnsensor'],
            'eq_heated_seats': ['oppvarmede seter', 'oppvarmede seter foran', 'oppvarmede seter bak',
                                'oppvarmede forseter', 'oppvarmede bakseter', 'varme i seter', 'setevarme foran',
                                'setevarme bak', 'setevarmer foran', 'setevarmer bak'],
            'eq_heated_steering_wheel': ['oppvarmet ratt', 'varmeratt', 'ratt oppvarmet'],
            'eq_electric_tailgate': ['elektrisk bakluke', 'el. bakluke', 'el bakluke', 'elektrisk bakdør'],
            'eq_electric_mirrors': ['el.mirroer', 'el speil', 'elektriske speil'],
            'eq_electric_windows': ['el.vinduer', 'el vinduer', 'elektriske vinduer',
                                    'vindusheiser elektriske foran og bak'],
            'eq_electric_seats': ['elektrisk seteregulering foran', 'elektrisk seteregulering bak',
                                  'el. seter foran', 'el. seter bak', 'elektriske seter', 'elektrisk sete'],
            'eq_heated_windshield': ['oppvarmet frontrute', 'oppvarmet vindu', 'oppvarmet vindusvisker'],
            'eq_winter_tires': ['vinterhjul', 'vinterdekk'],
            'eq_summer_tires': ['sommerhjul', 'sommerdekk'],
            'eq_multi_function_stearing_wheel': ['multifunksjonsratt'],
            'eq_block_heater': ['motorvarmer']
        }
        df = mk_bool_features(df, equipment_features, source_col='features')

        date_fields = ["last_eu", "next_eu", "last_updated"]
        for field in date_fields:
            if field in df.columns:
                df.loc[:, field] = df[field].apply(
                    lambda x: extract_datetime(x) if isinstance(x, str) else x)
                df[field] = pd.to_datetime(df[field])
            else:
                self.logger.warning(f'Field {field} missing from dataframe.')

        add_if_missing = ['web', 'email', 'warranty', 'color_interior', 'gearbox_type', 'warranty_length',
                          'condition_report']
        df = add_missing_features(df, add_if_missing)

        trouble_columns = ["last_eu", "next_eu"]
        for col in trouble_columns:
            if col in df.columns:
                df[col] = df[col].astype(str)

        self.logger.debug(f'Length: {len(df)} | before saving to BQ. Replace {self.replace}')
        self.df = df
        return df

    def pre_process(self, df=None, save_to_bq=True) -> tuple:
        if df is not None:
            self.df = df
        df = self.df.dropna(subset='item_id')
        df.drop_duplicates(subset=['item_id'], inplace=True)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on item_id')
        df.dropna(subset=['total_price', 'mileage', 'model_year'], inplace=True)

        drop = [
            'address', 'description', 'contact_person', 'phone', 'url', 'country', 'title', 'web', 'email',
            'municipality', 'rn', 'FIRST', 'LAST', 'postal_code', 'region', 'salgstid',
            'vin', 'reg_num', 'co2', 'color_description', 'first_registration', 'cargo_space', 'prev_owners',
            'last_eu', 'next_eu', 'trailer_weight', 'subtitle', 'warranty_until', 'known_issues', 'engine_tuned',
            'liens', 'major_repairs', 'state', 'battery', 'price_excl_transfer', 'clean_date', 'warranty',
            'color_interior', 'gearbox_type', 'warranty_length', 'condition_report'
        ]
        df.drop(columns=drop, inplace=True, errors='ignore')

        drop_eq = [x for x in df.columns if x.startswith('eq_') if x not in
                   ['eq_rear_view_camera', 'eq_bluetooth', 'eq_tow_hitch', 'eq_360_camera', 'eq_cruise_control',
                    'eq_parking_sensor_behind', 'eq_parking_sensor_front', 'eq_air_conditioning',
                    'eq_navigation', 'eq_winter_tires', 'eq_summer_tires',
                    'eq_skin_interior', 'eq_apple_carplay', 'eq_led_lights', 'eq_xenon_lights']]
        df.drop(columns=drop_eq, inplace=True, errors='ignore')

        df = rm_empty_features(df)
        self.logger.debug(f'Length of df: {len(df)} | after dropping NaN on price, usable_area and bedrooms')

        fuel_mapping = {
            'diesel': 'diesel', 'bensin': 'bensin', 'el': 'el', 'elektrisitet': 'el',
            'el + bensin': 'el + bensin', 'hybrid bensin': 'el + bensin',
            'plug-in bensin': 'el + bensin', 'el + diesel': 'el + diesel',
            'hybrid diesel': 'el + diesel', 'plug-in diesel': 'el + diesel',
            'hydrogen': 'hydrogen'
        }
        body_type_mapping = {
            'suv/offroad': 'flerbruksbil (af)', 'stasjonsvogn': 'stasjonsvogn (ac)',
            'kombi 5-dørs': 'kombikupé (ab)', '5': 'kombikupé (ab)',
            'kasse': 'integrert førerhus (bb)', 'sedan': 'sedan (aa)', 'annet': 'annet',
            'flerbruksbil': 'flerbruksbil (af)', 'coupe': 'kupé (ad)',
            'cabriolet': 'kabriolet (ae)', 'pickup': 'pick-up (be)',
            'kombi 3-dørs': 'kombikupé (ab)', '3': 'kombikupé (ab)'
        }
        brand_mapping = {
            'tesla motors': 'tesla', 'bmw i': 'bmw', 'alfa': 'alfa romeo',
            'jaguar land rover limited': 'land rover',
            'automobili lamborghini s.p.a.': 'lamborghini',
            'land': 'land rover', 'rover': 'land rover', 'range rover': 'land rover',
            'mercedes sprinter / kegger': 'mercedes-benz', 'mercedes-amg': 'mercedes-benz',
            'ford-cng-technik': 'ford', 'daimler': 'mercedes-benz',
            'kg mobility': 'kgm', 'mitsubishi fuso': 'mitsubishi',
            'jaguar cars limited': 'jaguar'
        }
        for col in ['fuel', 'body_type', 'brand']:
            df.loc[:, col] = df[col].str.lower()
            if col == 'fuel':
                df.loc[:, col] = df[col].map(fuel_mapping).fillna('annet')
            elif col == 'body_type':
                df.loc[:, col] = df[col].map(body_type_mapping).fillna('annet')
            elif col == 'brand':
                df.loc[:, col] = df[col].replace(brand_mapping)

        df['dealer'] = df['dealer'].apply(lambda x: False if x.lower() == 'private' else True)
        df = process_bool(df)
        self.logger.debug(f'Length of df: {len(df)} | after mapping categories and creating dummy variables')

        col_valid_values = {
            'fuel': ['el + bensin', 'diesel', 'el', 'bensin'],
            'gearbox': ['automat', 'manuell'],
            'color': ['svart', 'grå', 'rød', 'blå', 'sølv', 'grønn', 'brun', 'hvit'],
            'wheel_drive': ['forhjulsdrift', 'firehjulsdrift', 'bakhjulsdrift'],
            'body_type': ['flerbruksbil (af)', 'stasjonsvogn (ac)', 'kombikupé (ab)',
                          'integrert førerhus (bb)', 'sedan (aa)', 'pick-up (be)', 'kupé (ad)', 'annet'],
            'sales_type': ['bruktbil til salgs', 'auksjon', 'nybil til salgs'],
            'brand': ['ford', 'skoda', 'bmw', 'volvo', 'peugeot', 'mercedes-benz',
                      'volkswagen', 'kia', 'toyota', 'audi', 'porsche', 'citroen',
                      'opel', 'nissan', 'renault', 'hyundai', 'mazda', 'tesla',
                      'mitsubishi', 'suzuki'],
            'county': ['rogaland', 'innlandet', 'buskerud', 'akershus', 'møre og romsdal',
                       'vestfold', 'oslo', 'vestland', 'nordland', 'trøndelag', 'agder',
                       'østfold', 'telemark', 'troms'],
            'category': ['personbil', 'varebil']
        }
        for col, valid_values in col_valid_values.items():
            df = mk_cat(df, col, valid_values)

        self.logger.debug(f'Length of df: {len(df)} | after mapping and removing unwanted categories')
        df = df[df['sales_type'] != 'leasing']
        self.logger.debug(f'Length of df: {len(df)} | after dummy variables')

        df['n_features'] = df['features'].apply(lambda x: len(x.split(',')) if isinstance(x, str) else 0)
        df.drop(columns=['features'], inplace=True, errors='ignore')

        df = split_date(df, date_col='scrape_date')
        df = split_date(df, date_col='last_updated')
        df['pre_processed_date'] = pd.Timestamp.now()
        self.logger.debug(f'Length of df: {len(df)} | after date columns')

        df = ensure_num_types(df, num_types=['int', 'float'])

        df_el = df[df['fuel'] == 'el']
        df_fossil = df[df['fuel'] != 'el']

        df_el["range"] = df_el["range"].astype("Int64")
        df_el.dropna(subset=['range'], inplace=True)
        df_el.drop(columns=['engine_volume'], inplace=True, errors='ignore')
        df_el = rm_nan_cols(df_el)
        self.logger.debug(f'Length of df_el: {len(df_el)} | before saving to BQ. Replace is {self.replace}')

        if save_to_bq and not df_el.empty:
            self.save_data(df=df_el, table_name=f'{self.dataset}_el')

        df_fossil = df_fossil.drop(columns=['range'], errors='ignore')
        df_fossil = rm_nan_cols(df_fossil)
        self.logger.debug(f'Length of df_fossil: {len(df_fossil)} | Before saving to BQ. Replace is {self.replace}')

        if save_to_bq and not df_fossil.empty:
            self.save_data(df=df_fossil, table_name=f'{self.dataset}_fossil',
                           explicit_schema={"range": "INT"})

        return df_el, df_fossil

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
