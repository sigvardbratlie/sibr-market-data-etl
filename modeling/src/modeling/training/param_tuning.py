import numpy as np
import pandas as pd
import sklearn
import matplotlib.pyplot as plt
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
import logging
logger = logging.getLogger(__name__)

class ParamTuning:
    def __init__(self, dataset_name: str, dataframe: pd.DataFrame, target: str,
                 model_params: dict, logger: logging.Logger = None, log_target: bool = False):
        if not logger:
            logger = logging.getLogger('model_selection')
        logger = logger
        self.target = target
        self.model_params = model_params
        self.all_results = []
        self.df = dataframe
        self.dataset_name = dataset_name
        self.log_target = log_target

    def load_data(self):
        X = self.df.drop(columns=[self.target], axis=1)
        y = np.log1p(self.df[self.target]) if self.log_target else self.df[self.target]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        logger.info(f"Train set size: {X_train.shape[0]}, Test set size: {X_test.shape[0]}")
        logger.info(f'Columns in train set: {X_train.columns.tolist()}')
        return X_train, X_test, y_train, y_test

    def training_step(self, model_name: str, model, params, data: tuple,
                      pipe: sklearn.pipeline.Pipeline = None,
                      n_iter=50, cv=3, scoring='neg_mean_squared_error'):
        X_train, X_test, y_train, y_test = data
        results = {
            'train_loss': 0, 'test_loss': 0, 'r2_score': 0,
            'model_name': model_name, 'dataset_name': self.dataset_name
        }
        logger.info(f'Training {model_name} model with hyperparameter tuning. Dataset: {self.dataset_name}')
        if pipe is None:
            pipe = Pipeline([
                ('impute', SimpleImputer()),
                ('scaler', StandardScaler()),
                ('model', model),
            ])
        cv_search = RandomizedSearchCV(pipe, param_distributions=params, n_iter=n_iter, cv=cv,
                                       scoring=scoring, verbose=1, random_state=42, n_jobs=-1,
                                       refit=scoring, return_train_score=True)
        try:
            cv_search.fit(X_train, y_train)
            y_pred = cv_search.predict(X_test)
            y_pred_train = cv_search.predict(X_train)
            mse = mean_squared_error(np.expm1(y_test), np.expm1(y_pred)) if self.log_target else mean_squared_error(
                y_test, y_pred)
            mse_train = mean_squared_error(np.expm1(y_train),
                                           np.expm1(y_pred_train)) if self.log_target else mean_squared_error(y_train,
                                                                                                               y_pred_train)
            r2 = r2_score(np.expm1(y_test), np.expm1(y_pred)) if self.log_target else r2_score(y_test, y_pred)
            r2_train = r2_score(np.expm1(y_train),
                                np.expm1(y_pred_train)) if self.log_target else r2_score(y_train, y_pred_train)
            logger.info(f'{model_name} model best parameters: {cv_search.best_params_} on {self.dataset_name}')
            logger.info(
                f'Best score for {model_name}: Train: {mse_train}, Test: {mse}, R2 (test): {r2}, R2 (train): {r2_train} on {self.dataset_name} \n')
            results['dataset_name'] = self.dataset_name
            results['model_name'] = model_name
            results['train_loss'] = mse_train
            results['test_loss'] = mse
            results['r2_test'] = r2
            results['r2_train'] = r2_train
            results['params'] = cv_search.best_params_
            results['best_model'] = cv_search.best_estimator_
            self.all_results.append(results)
        except Exception as e:
            logger.error(f'Error training {model_name} model: {e}')

    def model_selection(self, models: dict, cv=3, n_iter=50, scoring='neg_mean_squared_error'):
        logger.info(f'\n \n -------- MODEL SELECTION FOR {self.dataset_name.upper()} --------')
        X_train, X_test, y_train, y_test = self.load_data()
        for model_name, (model, params) in models.items():
            self.training_step(model_name=model_name, model=model, params=params,
                               data=(X_train, X_test, y_train, y_test), cv=cv,
                               n_iter=n_iter, scoring=scoring)
        logger.info(f' \n ===== RESULTS FOR {self.dataset_name} =====')
        for res in self.all_results:
            logger.info(
                f'Model: {res.get("model_name")} | r2_test {res.get("r2_test")} | r2_train {res.get("r2_train")} \t | \t PARAMETERS {res.get("params")}')

    def get_feat_imp(self, model_idx: int) -> tuple:
        model = self.all_results[model_idx].get('best_model')['model']
        data = model.feature_importances_
        feat_names = self.all_results[model_idx].get('best_model')['impute'].feature_names_in_
        feat_imp = pd.DataFrame(data, index=feat_names, columns=['importance']).sort_values('importance',
                                                                                             ascending=False)
        not_important = feat_imp[feat_imp['importance'] == 0].index.tolist()
        return feat_imp, not_important

    def plot_feat_imp(self, model_index: int, show_top_n=15):
        feat_imp, _ = self.get_feat_imp(model_idx=model_index)
        fig = plt.figure(figsize=(16, 6))
        plt.bar(x=feat_imp['importance'].index[:show_top_n], height=feat_imp['importance'][:show_top_n])
        plt.xticks(rotation=45, ha='right')
        plt.show()
