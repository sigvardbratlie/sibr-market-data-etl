import os
import random
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error, r2_score
from xgboost import XGBRegressor
from catboost import CatBoostRegressor
from modeling.base import SibrBase

import logging
logger = logging.getLogger(__name__)

class Trainer(SibrBase):
    def __init__(self, dataset,log_target=True):
        super().__init__(dataset=dataset,)
        self.task_name = 'train'
        self.replace = False
        self.log_target = log_target

    def load_data(self, df, target, log_target):
        X = df.drop(columns=[target], axis=1)
        y = np.log1p(df[target]) if log_target else df[target]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)
        logger.info(f"📊 Train: {X_train.shape[0]} rows | Test: {X_test.shape[0]} rows")
        logger.info(f"🎯 Target: {target} | log_target: {log_target}")
        return X_train, X_test, y_train, y_test

    def save_model(self, pipeline, results: dict, data_name: str):
        model_name = pipeline.steps[-1][1].__class__.__name__
        filename_bucket = f'models/{model_name}_{data_name}.pkl'
        manifest_filename = 'models.json'
        local_manifest_path = f'/tmp/{manifest_filename}'

        results['filename'] = filename_bucket
        results['model_type'] = model_name
        new_model_info = pd.DataFrame([results])

        try:
            self.gcs_download(manifest_filename, local_path=local_manifest_path)
            all_models_df = pd.read_json(local_manifest_path, orient='records')

            if data_name in all_models_df['dataset'].values:
                logger.info(f"♻️  Updating model '{data_name}' in manifest.")
                all_models_df = all_models_df[all_models_df['dataset'] != data_name]
            all_models_df = pd.concat([all_models_df, new_model_info], ignore_index=True)
            all_models_df.drop_duplicates(subset=['dataset'], keep='last', inplace=True)
        except Exception as e:
            logger.info(f"📋 Manifest '{manifest_filename}' not found — creating new. ({e})")
            all_models_df = new_model_info

        all_models_df.to_json(local_manifest_path, orient='records')
        self.gcs_upload(local_manifest_path, manifest_filename)

        local_filepath = f'/tmp/tmp_file.pkl'
        joblib.dump(pipeline, local_filepath)
        try:
            self.gcs_upload(local_filepath, filename_bucket)
        finally:
            os.remove(local_filepath)

    def calc_scores(self, true, pred, log_target: bool) -> tuple:
        r2 = r2_score(np.expm1(true), np.expm1(pred)) if log_target else r2_score(true, pred)
        mse = mean_squared_error(np.expm1(true), np.expm1(pred)) if log_target else mean_squared_error(true, pred)
        return mse, r2

    def get_cat(self, df):
        cat_cols = []
        cat_idx = []
        for idx, (col, dtype) in enumerate(df.dtypes.items()):
            if dtype == 'object' or dtype == 'category' or dtype == 'string':
                cat_cols.append(col), cat_idx.append(idx)
        return cat_cols, cat_idx

    def train(self, df, params, data_name, model, target, save_to_gc=True, categorical=False, log_target=None):
        logger.info(f'🤖 Training {model().__class__.__name__} for {data_name.upper()}')
        if not log_target:
            log_target = self.log_target
        X_train, X_test, y_train, y_test = self.load_data(df=df, target=target, log_target=log_target)

        cat_cols, cat_idx = self.get_cat(X_train)
        num_cols = X_train.select_dtypes(include=[np.number, 'bool', 'boolean']).columns.tolist()

        num_trans = Pipeline(steps=[('impute', SimpleImputer(strategy='mean'))])
        cat_trans = Pipeline(steps=[('impute', SimpleImputer(strategy='most_frequent'))])

        if categorical:
            pre_processer = ColumnTransformer(
                transformers=[('num', num_trans, num_cols), ('cat', cat_trans, cat_cols)],
                remainder='passthrough')
            cat_features_indices = list(range(len(num_cols), len(num_cols) + len(cat_cols)))
            pipeline = Pipeline([
                ('pre_processor', pre_processer),
                ('model', CatBoostRegressor(cat_features=cat_features_indices, verbose=0)),
            ])
            pipeline_params = {'model__' + key: value for key, value in params.items()}
            pipeline.set_params(**pipeline_params)
        else:
            pre_processer = ColumnTransformer(
                transformers=[('num', num_trans, num_cols)], remainder='passthrough')
            pipeline = Pipeline([('pre_processor', pre_processer), ('model', model())])
            pipeline.set_params(**params)

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        y_pred_train = pipeline.predict(X_train)
        mse, r2 = self.calc_scores(y_test, y_pred, log_target=log_target)
        mse_train, r2_train = self.calc_scores(y_train, y_pred_train, log_target=log_target)

        training_columns = {}
        for col, dtype in X_train.dtypes.items():
            tries = 0
            sample = None
            while sample is None or sample is np.nan:
                sample_idx = random.randint(0, len(X_train[col]) - 1)
                sample = X_train[col].iloc[sample_idx]
                tries += 1
                if tries > 1000:
                    break
            training_columns[col] = (str(dtype), sample)

        logger.info(f'📊 {data_name} — Test: MSE={mse:.2f}, R²={r2:.4f} | Train: MSE={mse_train:.2f}, R²={r2_train:.4f} | target={target}, log={log_target}')
        results = {
            'dataset': data_name,
            'target': target,
            'log_target': log_target,
            'created_at': pd.Timestamp.now(),
            'training_columns': training_columns,
            'params': str(params),
            'r2_score': r2,
            'mse': mse,
            'mse_train': mse_train,
            'r2_train': r2_train
        }
        if save_to_gc:
            self.save_model(pipeline, results=results, data_name=data_name)
        return pipeline

    def rm_coor_outliers(self, df):
        df = df[(df['lat'] > 57.5) & (df['lat'] < 71.5)
                & (df['lng'] > 4) & (df['lng'] < 31)]
        return df

    def run(self, save_to_gc=True):
        logger.info(f'🚀 Running {self.task_name} for: {self.dataset} | save_to_gc={save_to_gc}')
        if self.dataset == 'homes':
            data = self.bq.read_homes(task="train")
            df_a = data.get("homes_apartments")
            df_h = data.get("homes_houses")
            df_o = data.get("homes_oslo")
            params_a = {'model__learning_rate': np.float64(0.02545642421255076), 'model__max_depth': 5,
                        'model__n_estimators': 1060, 'model__random_state': 98,
                        'model__subsample': np.float64(0.6478376983753207)}
            params_h = {'model__learning_rate': np.float64(0.03233791944457942), 'model__max_depth': 3,
                        'model__n_estimators': 1253, 'model__random_state': 52,
                        'model__subsample': np.float64(0.7957811041110252)}
            params_o = {'model__learning_rate': np.float64(0.03750796359625606), 'model__max_depth': 4,
                        'model__n_estimators': 978, 'model__random_state': 52,
                        'model__subsample': np.float64(0.8347004662655393)}
            pipeline_a = self.train(df=df_a, params=params_a, target='price',
                                    data_name='homes_apartments', model=XGBRegressor,
                                    save_to_gc=save_to_gc, log_target=True)
            pipeline_h = self.train(df=df_h, params=params_h, target='price',
                                    data_name='homes_houses', model=XGBRegressor,
                                    save_to_gc=save_to_gc, log_target=True)
            pipeline_o = self.train(df=df_o, params=params_o, target='price',
                                    data_name='homes_apartments_oslo', model=XGBRegressor,
                                    save_to_gc=save_to_gc, log_target=True)
            return pipeline_a, pipeline_h, pipeline_o

        elif self.dataset == 'rentals':
            data = self.bq.read_rentals(task="train")
            df_a = data.get("rentals")
            df_co = data.get("rentals_co-living")
            df_o = data.get("rentals_oslo")
            df_a = self.rm_coor_outliers(df_a)
            df_co = self.rm_coor_outliers(df_co)
            df_o = self.rm_coor_outliers(df_o)
            params_rentals = {'model__depth': 7, 'model__iterations': 1223,
                                'model__l2_leaf_reg': np.float64(1.3895264494261033),
                                'model__learning_rate': np.float64(0.09150423569345205), 'model__random_state': 52}
            params_co = {'model__depth': 9, 'model__iterations': 809,
                            'model__l2_leaf_reg': np.float64(3.241509528627272),
                            'model__learning_rate': np.float64(0.04135867955263894), 'model__random_state': 36}
            params_o = {'model__depth': 9, 'model__iterations': 809,
                        'model__l2_leaf_reg': np.float64(3.241509528627272),
                        'model__learning_rate': np.float64(0.04135867955263894), 'model__random_state': 36}
            pipeline_rentals = self.train(df=df_a, params=params_rentals, target='monthly_rent',
                                            data_name='rentals', model=CatBoostRegressor,
                                            save_to_gc=save_to_gc, log_target=True)
            pipeline_rental_oslo = self.train(df=df_o, params=params_o, target='monthly_rent',
                                                data_name='rentals_oslo', model=CatBoostRegressor,
                                                save_to_gc=save_to_gc, log_target=True)
            pipeline_coliv = self.train(df=df_co, params=params_co, target='monthly_rent',
                                        data_name='rentals_co-living', model=CatBoostRegressor,
                                        save_to_gc=save_to_gc, log_target=True)
            return pipeline_rentals, pipeline_rental_oslo, pipeline_coliv

        elif self.dataset == 'cars':
            data = self.bq.read_cars(task="train")
            df_el = data.get("cars_el")
            df_fossil = data.get("cars_fossil")
            df_el.dropna(inplace=True)
            df_fossil.dropna(inplace=True)
            logger.info(f'📊 After dropna — cars_el: {len(df_el)} rows | cars_fossil: {len(df_fossil)} rows')
            params_el = {'depth': 7, 'iterations': 1223, 'l2_leaf_reg': np.float64(1.3895264494261033),
                            'learning_rate': np.float64(0.09150423569345205), 'random_state': 52}
            params_fossil = {'depth': 4, 'iterations': 1463, 'l2_leaf_reg': np.float64(1.7419090119209117),
                                'learning_rate': np.float64(0.10215580871496355), 'random_state': 43}
            pipeline_el = self.train(df=df_el, params=params_el, target='total_price',
                                        data_name='cars_el', model=CatBoostRegressor,
                                        save_to_gc=save_to_gc, categorical=True, log_target=True)
            pipeline_fossil = self.train(df=df_fossil, params=params_fossil, target='total_price',
                                            data_name='cars_fossil', model=CatBoostRegressor,
                                            save_to_gc=save_to_gc, categorical=True, log_target=True)
            return pipeline_el, pipeline_fossil


# Backward-compatible alias
Train = Trainer
