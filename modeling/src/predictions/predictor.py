import numpy as np
import pandas as pd
import sklearn
from ..base import SibrBase

import logging
logger = logging.getLogger(__name__)

class Predictor(SibrBase):
    def __init__(self, dataset, log_target=True):
        super().__init__(dataset=dataset)
        self.task_name = 'predictions'
        self.replace = True
        self.log_target = log_target

    def ensure_columns(self, df, training_columns, data_name=None):
        for col in training_columns:
            if col not in df.columns:
                logger.warning(f'Column {col} not in dataframe for {data_name}. Adding it.')
                df[col] = False
        return df[training_columns]

    def predict_data(self, dataframe, pipeline: sklearn.pipeline.Pipeline, model_results):
        log_target = model_results.get('log_target')
        if not log_target:
            log_target = self.log_target
        X = dataframe.drop(columns=[model_results.get('target')], axis=1)
        X = self.ensure_columns(df=X, training_columns=list(model_results.get('training_columns').keys()),
                                data_name=model_results.get('dataset'))
        y_pred = np.expm1(pipeline.predict(X)) if log_target else pipeline.predict(X)
        return y_pred

    def rm_other_outliers(self, df):
        if 'bedrooms' in df.columns and 'monthly_rent' in df.columns:
            drop_item_ids = df[(df['bedrooms'] == 0) & (df['monthly_rent'] > 20000)]
            df = df[~df['item_id'].isin(drop_item_ids['item_id'])]
        return df

    def rm_coor_outliers(self, df):
        df = df[(df['lat'] > 57.5) & (df['lat'] < 71.5)
                & (df['lng'] > 4) & (df['lng'] < 31)]
        return df

    def run(self, save_to_bq=True):
        logger.info(f'RUNNING {self.task_name} for dataset: {self.dataset}. Save to BQ is {save_to_bq}')
        models_json = self.cs.download('models.json', read_in_file=True)
        models = pd.DataFrame.from_dict(models_json)
        models['created_at'] = pd.to_datetime(models['created_at'], unit='ms')
        if self.dataset == 'homes':
            data = self.bq.read_homes(task="predict")
            df_a = data.get("homes_apartments")
            df_h = data.get("homes_houses")
            df_o = data.get("homes_oslo")
            df_r = data.get("homes_rentals_oslo")

            df_a = self.rm_coor_outliers(df_a)
            df_h = self.rm_coor_outliers(df_h)
            df_o = self.rm_coor_outliers(df_o)
            df_r = self.rm_coor_outliers(df_r)

            add_columns = ['eq_power_True', 'eq_internet_True', 'eq_tv_True', 'eq_fiber_True',
                            'eq_hot_water_True', 'eq_heating_True', 'parking_True']
            for col in add_columns:
                df_r[col] = True if col == 'eq_internet_True' else False

            res_a = models[models['dataset'] == 'homes_apartments'].iloc[0].to_dict()
            res_h = models[models['dataset'] == 'homes_houses'].iloc[0].to_dict()
            res_o = models[models['dataset'] == 'homes_apartments_oslo'].iloc[0].to_dict()
            res_r = models[models['dataset'] == 'rentals_oslo'].iloc[0].to_dict()

            m_a = self.cs.download(res_a.get('filename'), read_in_file=True)
            m_h = self.cs.download(res_h.get('filename'), read_in_file=True)
            m_o = self.cs.download(res_o.get('filename'), read_in_file=True)
            m_r = self.cs.download(res_r.get('filename'), read_in_file=True)

            y_pred_a = self.predict_data(dataframe=df_a, pipeline=m_a, model_results=res_a)
            y_pred_h = self.predict_data(dataframe=df_h, pipeline=m_h, model_results=res_h)
            y_pred_o = self.predict_data(dataframe=df_o, pipeline=m_o, model_results=res_o)
            df_r = self.ensure_columns(df=df_r,
                                        training_columns=list(res_r.get('training_columns').keys()),
                                        data_name='rentals_oslo')
            y_pred_r = np.log1p(m_r.predict(df_r)) if res_r.get('log_target') else m_r.predict(df_r)

            df_a_rehab = df_a[df_a['fixer_upper_True'] == True].copy()
            df_a_rehab['fixer_upper_True'] = False
            y_pred_rehab = self.predict_data(dataframe=df_a_rehab, pipeline=m_a, model_results=res_a)

            df_o_rehab = df_o[df_o['fixer_upper_True'] == True].copy()
            df_o_rehab['fixer_upper_True'] = False
            y_pred_rehab_o = self.predict_data(dataframe=df_o_rehab, pipeline=m_o, model_results=res_o)

            pred_a = pd.DataFrame({'item_id': df_a.index, 'predicted_price': y_pred_a, 'model': 'apartments'})
            pred_h = pd.DataFrame({'item_id': df_h.index, 'predicted_price': y_pred_h, 'model': 'houses'})
            pred_o = pd.DataFrame({'item_id': df_o.index, 'predicted_price': y_pred_o, 'model': 'apartments_oslo'})
            pred_r = pd.DataFrame({'item_id': df_r.index, 'predicted_price': y_pred_r, 'model': 'rentals_oslo'})
            pred_a_rehab = pd.DataFrame(
                {'item_id': df_a_rehab.index, 'predicted_price': y_pred_rehab, 'model': 'homes_rehab'})
            pred_o_rehab = pd.DataFrame(
                {'item_id': df_o_rehab.index, 'predicted_price': y_pred_rehab_o, 'model': 'homes_rehab_oslo'})

            pred = pd.concat([pred_a, pred_h, pred_o, pred_a_rehab, pred_o_rehab])
            pred['predict_date'] = pd.Timestamp.now()
            pred_r['predict_date'] = pd.Timestamp.now()

            if save_to_bq:
                if not pred.empty:
                    self.save_data(df=pred, table_name=self.dataset)
                if not pred_r.empty:
                    self.save_data(df=pred_r, table_name='homes_rentals')
            else:
                logger.warning('No data saved to BQ as save_to_bq is set to False.')

        if self.dataset == 'cars':
            data = self.bq.read_cars(task="predict")
            df_el = data.get("cars_el")
            df_fossil = data.get("cars_fossil")

            res_el = models[models['dataset'] == 'cars_el'].iloc[0].to_dict()
            res_fossil = models[models['dataset'] == 'cars_fossil'].iloc[0].to_dict()
            m_el = self.cs.download(res_el.get('filename'), read_in_file=True)
            m_fossil = self.cs.download(res_fossil.get('filename'), read_in_file=True)

            y_pred_el = self.predict_data(dataframe=df_el, pipeline=m_el, model_results=res_el)
            y_pred_fossil = self.predict_data(dataframe=df_fossil, pipeline=m_fossil, model_results=res_fossil)

            pred_el = pd.DataFrame({'item_id': df_el.index, 'predicted_price': y_pred_el, 'model': 'el'})
            pred_fossil = pd.DataFrame(
                {'item_id': df_fossil.index, 'predicted_price': y_pred_fossil, 'model': 'fossil'})
            pred = pd.concat([pred_el, pred_fossil], ignore_index=False)
            pred['predict_date'] = pd.Timestamp.now()

            if save_to_bq:
                if not pred.empty:
                    self.save_data(df=pred, table_name=self.dataset)
            else:
                logger.warning('No data saved to BQ as save_to_bq is set to False.')


# Backward-compatible alias
Predict = Predictor
