import re
import numpy as np
import pandas as pd
from .transformers import extract_int, extract_float


def mk_num(df, int_cols, type='int') -> pd.DataFrame:
    """Convert columns to numeric (int or float), extracting numbers from strings."""
    if type not in ['int', 'float']:
        raise ValueError(f'Type "{type}" is not allowed. Must be "int" or "float".')
    for col in int_cols:
        if col in df.columns:
            if type == 'int':
                new = df[col].apply(lambda x: extract_int(x) if isinstance(x, str) else x)
                df[col] = pd.to_numeric(new, errors='coerce').astype('Int64', errors='ignore')
            elif type == 'float':
                new = df[col].apply(lambda x: extract_float(x) if isinstance(x, str) else x)
                df[col] = pd.to_numeric(new, errors='coerce').astype('Float64', errors='ignore')
    return df


def mk_cat(df, col, valid_values) -> pd.DataFrame:
    """Convert a column to a categorical type with specified valid values."""
    df[col] = df[col].apply(lambda x: x.lower() if isinstance(x, str) else x)
    valid_values = [x.lower() for x in valid_values if isinstance(x, str)]
    isin = df[col].isin(valid_values)
    df = df[isin].copy()
    df.loc[:, col] = df[col].astype(str)
    df.loc[:, col] = pd.Categorical(df[col], categories=valid_values, ordered=False)
    return df


def ensure_num_types(df, num_types=None) -> pd.DataFrame:
    """Ensure numeric columns have correct pandas nullable dtypes."""
    if num_types is None:
        num_types = ['int', 'float']
    if not isinstance(num_types, list):
        raise ValueError(f'num_types must be a list, got {type(num_types)} instead.')
    if not all(dtype in ['int', 'float'] for dtype in num_types):
        raise ValueError(f'num_types must contain only "int" and "float", got {num_types} instead.')
    if num_types == ['int']:
        for col, dtype in df.dtypes.items():
            if dtype in ('Float64', 'float64', 'float32', 'int32'):
                df[col] = df[col].astype('Int64', errors='ignore')
    elif num_types == ['int', 'float']:
        for col, dtype in df.dtypes.items():
            if dtype in ('Float64', 'float64', 'float32'):
                df[col] = df[col].astype('Float64', errors='ignore')
            elif dtype in ('int32', 'int64'):
                df[col] = df[col].astype('Int64', errors='ignore')
    elif num_types == ['float']:
        for col, dtype in df.dtypes.items():
            if dtype in ('Float64', 'float64', 'float32', 'int32'):
                df[col] = df[col].astype('Float64', errors='ignore')
    return df


def transform_nan(df) -> pd.DataFrame:
    """Remove duplicates on item_id and replace null-like string values with np.nan."""
    df = df.drop_duplicates(subset='item_id').copy()
    values_to_replace = ['nan', 'None', '', 'null', 'NA', 'np.nan', '<NA>', 'NaN', 'NAType']
    cols_to_fix = df.select_dtypes(include=['object', 'string']).columns
    df[cols_to_fix] = df[cols_to_fix].replace(values_to_replace, np.nan)
    
    return df


def fill_na(df, feature, fill_value) -> pd.DataFrame:
    """Fill missing values in a column, coercing fill_value to the column dtype."""
    if feature in df.columns:
        try:
            if pd.api.types.is_any_real_numeric_dtype(df[feature]):
                fill_value = float(fill_value)
            elif pd.api.types.is_bool_dtype(df[feature]):
                fill_value = bool(fill_value)
            elif pd.api.types.is_string_dtype(df[feature]):
                fill_value = str(fill_value)
            elif pd.api.types.is_object_dtype(df[feature]):
                fill_value = str(fill_value)
        except (ValueError, TypeError):
            pass
        df.loc[:, feature] = df[feature].fillna(fill_value)
    else:
        df[feature] = fill_value
    return df


def rm_empty_features(df, threshold=0.9) -> pd.DataFrame:
    """Drop columns where more than `threshold` fraction of values are missing."""
    for col in df.columns:
        if df[col].isna().sum() / len(df) > threshold:
            df.drop(col, axis=1, inplace=True)
    return df


def add_missing_features(df: pd.DataFrame, missing_features: list) -> pd.DataFrame:
    """Add columns with None values if they don't exist in the DataFrame."""
    for col in missing_features:
        if col not in df.columns:
            df[col] = None
    return df


def mk_fractions(df, new_feat_name, numerator, denominator) -> pd.DataFrame:
    """Create a new column as the ratio of two existing columns."""
    df[new_feat_name] = df.apply(
        lambda x: x[numerator] / x[denominator]
        if pd.notna(x[denominator]) and pd.notna(x[numerator]) and x[denominator] > 0
        else np.nan,
        axis=1
    )
    return df


def split_date(df, date_col: str) -> pd.DataFrame:
    """Convert a datetime column to year/month/day integer columns and drop the original."""
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df['day'] = df[date_col].dt.day
    df['month'] = df[date_col].dt.month
    df['year'] = df[date_col].dt.year
    df.drop(date_col, axis=1, inplace=True)
    return df


def mk_bool_description(df: pd.DataFrame, col_name: str, keys: list,
                        source_cols=None) -> pd.DataFrame:
    """Create a boolean column that is True if any keyword is found in the source columns."""
    if source_cols is None:
        source_cols = ['description']
    if isinstance(source_cols, str):
        source_cols = [source_cols]

    regex = '|'.join(re.escape(key) for key in keys)
    pattern = re.compile(regex, re.IGNORECASE)

    df[col_name] = False
    for source_col in source_cols:
        if source_col in df.columns:
            matches = df[source_col].str.contains(pattern, regex=True, na=False)
            df[col_name] = df[col_name] | matches

    df[col_name] = df[col_name].astype('boolean')
    return df


def mk_bool_features(df: pd.DataFrame, equipment_features: dict,
                     source_col='features') -> pd.DataFrame:
    """Create boolean columns from a feature dictionary by searching a list-like column."""
    df.loc[:, source_col] = df[source_col].apply(
        lambda x: [item.strip().strip("'\"").lower()
                   for item in (x.replace("]", "").replace("[", "").split(',')
                                if isinstance(x, str) else [])
                   if isinstance(item, str) and item.strip() != '']
    )

    feature_lookup = {}
    for feature_name, keywords in equipment_features.items():
        for keyword in keywords:
            if keyword not in feature_lookup:
                feature_lookup[keyword] = []
            feature_lookup[keyword].append(feature_name)

    feature_columns = {feature: np.zeros(len(df), dtype=bool) for feature in equipment_features}

    def process_row(idx, features_list):
        if not isinstance(features_list, list):
            return
        for feature in features_list:
            for keyword in feature_lookup:
                if keyword in feature:
                    for feature_name in feature_lookup[keyword]:
                        feature_columns[feature_name][idx] = True

    for idx, features_list in enumerate(df[source_col]):
        process_row(idx, features_list)

    for feature_name, values in feature_columns.items():
        df[feature_name] = values
    df[source_col] = df[source_col].astype(str)

    return df


def process_bool(df) -> pd.DataFrame:
    """Convert boolean columns to categorical and one-hot encode them (drop_first=True)."""
    bool_cols = []
    for col, dtype in df.dtypes.items():
        if dtype == 'bool' or dtype == 'boolean':
            bool_cols.append(col)
    for col in bool_cols:
        df[col] = df[col].astype('object').astype(str)
        df[col] = pd.Categorical(df[col], categories=['False', 'True'], ordered=False)
    df = pd.get_dummies(df, columns=bool_cols, drop_first=True)
    return df


def rm_nan_cols(df) -> pd.DataFrame:
    """Drop columns that are entirely NaN."""
    return df.dropna(axis=1, how='all')


def get_top_features(df, source_col='features'):
    """Extract and explode features from a list-like string column."""
    feat = df[source_col].apply(
        lambda x: x.lower().replace("]", "").replace("[", "").split(',') if isinstance(x, str) else [])
    feat = feat.apply(lambda x: [i.strip().strip("'\"") for i in x if isinstance(i, str) and i.strip() != ''])
    return feat.explode()
