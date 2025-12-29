# SIBR Market Backend - API

A data enrichment API service for geocoding addresses and fetching vehicle information from Norwegian public data sources. This component is part of the SIBR Market Backend system and handles external API integrations for the marketplace data pipeline.

## Overview

This API service provides automated data enrichment capabilities for marketplace listings, specifically:

- **Geocoding**: Convert property addresses to geographic coordinates using Norwegian geocoding services
- **Vehicle Data**: Fetch detailed vehicle information from the Norwegian Public Roads Administration (Statens Vegvesen)

The service is designed to run as a scheduled job or on-demand process, enriching data stored in BigQuery and Firestore.

## Features

### Geocoding Services

The API supports two geocoding providers with automatic fallback:

1. **Geonorge** (Primary)
   - Official Norwegian mapping authority geocoding service
   - High accuracy for Norwegian addresses
   - Up to 30 concurrent requests

2. **Nominatim** (Fallback)
   - OpenStreetMap-based geocoding
   - Used for addresses that Geonorge cannot resolve
   - Up to 5 concurrent requests

The geocoding process automatically:
- Encodes addresses for URL-safe transmission
- Handles address format variations
- Tracks geocoding status (OK, NO_RESULTS)
- Stores coordinates with metadata in BigQuery

### Vehicle Information

Fetches comprehensive vehicle data from Statens Vegvesen API including:
- Registration details
- Technical specifications
- Vehicle history
- Inspection records

Results are stored in Firestore for efficient access.

## Architecture

The API is built on:

- **Async Processing**: Uses `asyncio` for concurrent API requests
- **Rate Limiting**: Respects API rate limits with configurable concurrent requests
- **Batch Processing**: Processes large datasets with periodic saves
- **Error Handling**: Graceful handling of missing data, rate limits, and API errors
- **Cloud Integration**: Direct integration with Google Cloud BigQuery and Firestore

## Prerequisites

- Python 3.12+
- Google Cloud Platform project with:
  - BigQuery access
  - Firestore access
  - Service account credentials
- Statens Vegvesen API key (for vehicle data)

## Installation

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```env
GOOGLE_APPLICATION_CREDENTIALS_FILENAME=your-credentials-file.json
```

3. Ensure Google Cloud credentials are properly configured

### Docker Deployment

Build and run the Docker container:

```bash
docker build -t sibr-api .
docker run sibr-api --task all
```

## Usage

### Command Line Interface

The API is executed via command line with various options:

```bash
python main.py --task <task_name> [options]
```

#### Tasks

- `geocode`: Run geocoding process for addresses
- `statens-vegvesen`: Fetch vehicle data
- `all`: Run all tasks sequentially

#### Options

- `--address <address>`: Geocode a single address (testing)
- `--geocoder <geonorge|nominatim>`: Choose geocoding service (default: geonorge)
- `--limit <number>`: Limit number of records to process
- `--no-save`: Disable saving results (testing mode)
- `--use-proxy`: Use proxy for API requests
- `--log-level <level>`: Set logging level (default: INFO)
- `--cloud-logging`: Enable Google Cloud Logging

### Examples

Geocode all missing addresses:
```bash
python main.py --task geocode
```

Geocode with a limit:
```bash
python main.py --task geocode --limit 1000
```

Test a single address:
```bash
python main.py --task geocode --address "Karl Johans gate 1, Oslo" --geocoder geonorge
```

Fetch vehicle data:
```bash
python main.py --task statens-vegvesen --limit 50000
```

Run all tasks with cloud logging:
```bash
python main.py --task all --cloud-logging
```

## Configuration

### BigQuery Schema

The API expects the following BigQuery datasets and tables:

**Input Tables:**
- `sibr-market.clean.homes` - Property listings
- `sibr-market.clean.rentals` - Rental listings
- `sibr-market.clean.cars` - Vehicle listings

**Output Tables:**
- `sibr-market.staging.coordinates` - Geocoded coordinates

### Firestore Collections

- `statens_vegvesen` - Vehicle data from Statens Vegvesen API

### Rate Limits

Configured in `main.py`:
- Nominatim: 5 concurrent requests
- Geonorge: 30 concurrent requests
- Statens Vegvesen: 50,000 requests per day

## Project Structure

```
api/
├── main.py              # Entry point and CLI interface
├── src/
│   ├── api.py          # Core API logic and data transformations
│   └── settings.py     # Configuration settings
├── examples/
│   └── examples.ipynb  # Usage examples and testing
├── Dockerfile          # Docker container definition
├── requirements.in     # Direct dependencies
└── requirements.txt    # Pinned dependencies
```

## Dependencies

Key dependencies include:

- **sibr-api**: Internal SIBR API framework
- **sibr-module**: Internal SIBR utilities (BigQuery, logging, secrets)
- **aiohttp**: Async HTTP client
- **pandas**: Data manipulation
- **geopandas**: Geospatial data handling
- **google-cloud-bigquery**: BigQuery client
- **google-cloud-firestore**: Firestore client
- **google-cloud-logging**: Cloud logging integration

## Data Flow

### Geocoding Process

1. Query BigQuery for addresses without coordinates
2. Batch process addresses through Geonorge API
3. Transform and validate responses
4. Save coordinates to BigQuery staging table
5. Retry failed addresses with Nominatim API
6. Log statistics and completion status

### Vehicle Data Process

1. Query BigQuery for cars without vehicle data
2. Check Firestore for already fetched records
3. Fetch remaining records from Statens Vegvesen API
4. Transform and validate vehicle data
5. Batch write to Firestore
6. Log progress and statistics

## Error Handling

The API handles various error scenarios:

- **Rate Limiting**: Catches `RateLimitError` and gracefully stops processing
- **Not Found**: Logs warnings for 404 errors, marks records appropriately
- **Invalid Data**: Validates and transforms responses, handling missing fields
- **Network Issues**: Configurable timeouts and retry logic

## Logging

Supports both local and cloud logging:

- Local: Console output with configurable log levels
- Cloud: Google Cloud Logging integration with `--cloud-logging` flag

Log messages include:
- Progress updates
- Success/failure counts
- API response statistics
- Warning messages for data quality issues

## Performance

The API is optimized for high-throughput processing:

- Asynchronous concurrent requests
- Batch saves (configurable intervals)
- Efficient data transformations with pandas
- Minimal memory footprint for large datasets

Typical performance:
- Geocoding: ~30 addresses/second (Geonorge)
- Vehicle data: ~30 records/second (Statens Vegvesen)

## Security

- API keys stored in Google Cloud Secret Manager
- Service account authentication for GCP resources
- Proxy support for anonymized requests
- No sensitive data in logs

## Limitations

- Statens Vegvesen API: 50,000 requests per day
- Nominatim: Subject to OpenStreetMap usage policies
- Geonorge: Limited to Norwegian addresses
- Processing time depends on data volume and API rate limits

## Future Improvements

Potential enhancements:
- Additional geocoding providers
- Caching layer for frequently requested addresses
- Real-time API endpoints
- Enhanced error recovery and retry logic
- Metrics and monitoring dashboard

## Related Components

This API component integrates with:
- **Scraping**: Provides raw data for geocoding
- **Modeling**: Uses enriched data for analysis
- **BigQuery**: Central data warehouse
- **Firestore**: Real-time data access

## Support

For issues or questions related to this API component, please refer to the main project documentation or contact the development team.
