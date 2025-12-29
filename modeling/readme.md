# SIBR Market - Modeling

Machine learning pipeline for price prediction and data processing for the SIBR Market platform. This module handles data cleaning, preprocessing, model training, and predictions for multiple market categories.

## Overview

The modeling component provides automated pipelines for:
- **Data Cleaning**: Processing and cleaning raw scraped data from BigQuery
- **Preprocessing**: Feature engineering and data transformation
- **Model Training**: Training machine learning models for price prediction
- **Predictions**: Generating price predictions for new listings

### Supported Datasets

- `cars` - Vehicle listings with training and prediction support
- `homes` - Real estate property listings with training and prediction support
- `rentals` - Rental property listings (cleaning only)
- `new_homes` - New home construction listings (cleaning only)

## Project Structure

```
modeling/
├── main.py                      # CLI entry point for all pipelines
├── src/
│   ├── sibr_market_training.py  # Core classes: Clean, Train, Predict
│   ├── helper_modules.py        # Utility functions and BigQuery helpers
│   ├── settings.py              # Project configuration
│   ├── cleaning/                # Data cleaning notebooks and modules
│   │   ├── common_functions.py
│   │   ├── clean-cars.ipynb
│   │   ├── clean-homes.ipynb
│   │   └── pre-processing-*.ipynb
│   ├── training/                # Model training notebooks and functions
│   │   ├── common_functions_training.py
│   │   ├── trainCars.ipynb
│   │   └── trainHomes.ipynb
│   ├── predictions/             # Prediction notebooks and utilities
│   │   ├── prediction_commonfunctions.py
│   │   ├── predictCars.ipynb
│   │   └── predictHomes.ipynb
│   └── model_selection/         # Model selection experiments
│       ├── modelSelection_Cars.ipynb
│       └── modelSelection_Homes.ipynb
├── examples/                    # Example notebooks and scripts
├── tests/                       # Unit tests
├── Dockerfile                   # Container configuration
└── requirements.txt             # Python dependencies
```

## Requirements

### Python Dependencies

Main libraries used:
- **ML Frameworks**: `xgboost`, `catboost`, `lightgbm`, `torch`
- **Data Processing**: `pandas`, `numpy`, `scikit-learn`
- **Google Cloud**: `google-cloud-bigquery`, `google-cloud-storage`, `google-cloud-logging`
- **Geospatial**: `geopy`, `shapely`, `geojson`
- **Custom**: `sibr-module` (internal SIBR utilities)

Install all dependencies:
```bash
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root with:
```
GOOGLE_APPLICATION_CREDENTIALS_FILENAME=your-credentials-file.json
```

For local development, place your Google Cloud service account key in the parent directory.

## Usage

### Command Line Interface

The `main.py` script provides a comprehensive CLI for running all pipeline tasks.

#### Basic Commands

**Clean a specific dataset:**
```bash
python main.py --dataset cars --task clean
```

**Preprocess data:**
```bash
python main.py --dataset homes --task pre_processed
```

**Train a model:**
```bash
python main.py --dataset cars --task train
```

**Generate predictions:**
```bash
python main.py --dataset homes --task predict
```

#### Batch Operations

**Clean all datasets:**
```bash
python main.py --run-clean
```

**Clean specific dataset:**
```bash
python main.py --run-clean --dataset cars
```

**Run all tasks for cars and homes (clean + preprocess + predict):**
```bash
python main.py --run_all
```

**Run all tasks including training:**
```bash
python main.py --run_all --run-train
```

#### Options and Flags

**Data Storage:**
- `--no_save` - Disable saving to BigQuery (useful for testing)
- `--replace` - Replace existing data in BigQuery tables

**Logging:**
- `--log-level DEBUG|INFO|WARNING|ERROR` - Set logging verbosity (default: DEBUG)
- `--cloud-logging` - Enable Google Cloud Logging

**Examples:**
```bash
# Test cleaning without saving to BigQuery
python main.py --dataset cars --task clean --no_save

# Replace existing data and enable cloud logging
python main.py --dataset homes --task pre_processed --replace --cloud-logging

# Run with minimal logging
python main.py --run_all --log-level WARNING
```

### Docker Deployment

**Build the image:**
```bash
docker build -t sibr-market-modeling .
```

**Run a task:**
```bash
docker run sibr-market-modeling --dataset cars --task train
```

**Mount credentials for local testing:**
```bash
docker run -v /path/to/credentials.json:/app/credentials.json \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  sibr-market-modeling --dataset homes --task predict
```

## Pipeline Architecture

### 1. Data Cleaning (`Clean`)

Processes raw scraped data from BigQuery:
- Removes duplicates and invalid entries
- Standardizes data formats
- Handles missing values
- Validates data quality

**Input**: Raw tables in BigQuery (from scraping pipeline)
**Output**: Cleaned tables in BigQuery

### 2. Preprocessing (`pre_processed`)

Feature engineering and transformation:
- Creates derived features
- Encodes categorical variables
- Normalizes numerical features
- Prepares data for model training

**Input**: Cleaned tables
**Output**: Preprocessed tables ready for ML

### 3. Model Training (`Train`)

Trains machine learning models:
- Uses XGBoost, CatBoost, or LightGBM
- Performs hyperparameter tuning
- Validates model performance
- Saves trained models to Google Cloud Storage

**Input**: Preprocessed data
**Output**: Trained model artifacts (.pkl files)

### 4. Prediction (`Predict`)

Generates price predictions:
- Loads latest trained model
- Processes new listings
- Generates predictions
- Stores results in BigQuery

**Input**: New listings data
**Output**: Predictions table in BigQuery

## Development Workflow

### Interactive Development

Use Jupyter notebooks in the `src/` subdirectories for exploratory work:

**Data Exploration:**
- `examples/EDA_cars.ipynb` - Exploratory data analysis

**Cleaning Development:**
- `src/cleaning/clean-*.ipynb` - Interactive cleaning notebooks

**Training Experiments:**
- `src/training/train*.ipynb` - Model training notebooks
- `src/model_selection/modelSelection_*.ipynb` - Model comparison

**Prediction Testing:**
- `src/predictions/predict*.ipynb` - Prediction notebooks

### Running Tests

```bash
pytest tests/
```

## Google Cloud Integration

### BigQuery Tables

**Raw Data**: `sibr-market.raw_data.*`
**Cleaned Data**: `sibr-market.cleaned_data.*`
**Preprocessed**: `sibr-market.preprocessed_data.*`
**Predictions**: `sibr-market.predictions.*`

### Cloud Storage

Models are stored in Google Cloud Storage:
- **Bucket**: `sibr-market`
- **Path**: `models/{dataset}/model.pkl`

### Cloud Logging

Enable with `--cloud-logging` flag for production deployments.

## Common Workflows

### Full Pipeline for New Dataset

```bash
# 1. Clean the data
python main.py --dataset cars --task clean

# 2. Preprocess
python main.py --dataset cars --task pre_processed

# 3. Train model
python main.py --dataset cars --task train

# 4. Generate predictions
python main.py --dataset cars --task predict
```

### Update Predictions Only

```bash
# Use existing model to predict new listings
python main.py --dataset homes --task predict
```

### Retrain with Fresh Data

```bash
# Clean, preprocess, and retrain
python main.py --dataset cars --task clean --replace
python main.py --dataset cars --task pre_processed --replace
python main.py --dataset cars --task train
```

## Troubleshooting

### Authentication Issues

Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set correctly:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

### Memory Issues

For large datasets, consider:
- Processing in batches
- Using a machine with more RAM
- Reducing the number of features

### BigQuery Quota Exceeded

Use `--no_save` flag for testing to avoid hitting quotas during development.

## Contributing

When adding new datasets or features:
1. Add dataset to `SUPPORTED_DATASETS` in `main.py`
2. Implement cleaning logic in `src/cleaning/`
3. Create training notebook in `src/training/`
4. Add prediction logic in `src/predictions/`
5. Update this README with new dataset information

## License

Internal SIBR Market project.
