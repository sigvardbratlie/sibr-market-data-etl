# SIBR Market Backend - Cadastral

A data enrichment service for fetching Norwegian property cadastral information, ownership records, and transfer history from Kartverket's Grunnbok API. This component is part of the SIBR Market Backend system and provides comprehensive property ownership data for marketplace listings.

## Overview

This service integrates with Kartverket (Norwegian Mapping Authority) to retrieve official cadastral records including:

- **Property Ownership**: Current and historical ownership information for real estate properties
- **Transfer Records**: Property transfer history including transaction details and dates
- **Cooperative Housing**: Ownership information for cooperative housing units (borettslag)
- **Legal Status**: Property rights, mortgages, and other legal annotations

The service is designed to run as a batch processing job, enriching property data stored in BigQuery with official cadastral information.

## Features

### Property Types

The service handles two main types of property ownership:

1. **Traditional Ownership (Eier)**
   - Properties identified by cadastral numbers (kommunenummer, gaardsnummer, bruksnummer)
   - Includes freehold properties, condominiums, and leasehold properties
   - Supports section numbers for apartment units

2. **Cooperative Housing (Andel)**
   - Cooperative housing units identified by organization and unit numbers
   - Specific to Norwegian housing cooperatives (borettslag/boligselskap)

### Transfer Types

Supports fetching both:
- **Active Transfers**: Current ownership and active legal rights
- **Historical Transfers**: Complete historical record of ownership changes

### Processing Modes

- **Fill Mode**: Only processes properties missing cadastral data
- **Overwrite Mode**: Updates existing records for recent properties (last 300 days)
- **Batch Processing**: Handles large datasets with configurable batch sizes

## Architecture

The service is built on:

- **Async Processing**: Asynchronous API calls using `asyncio` and `aiohttp`
- **Batch Operations**: Configurable batch sizes (default 50,000 properties)
- **Cloud Integration**: Direct integration with Google Cloud BigQuery
- **External API**: Kartverket's Grunnbok API via the `kartverkets-api` package
- **Deduplication**: Automatic handling of duplicate records per property

## Prerequisites

- Python 3.12+
- Google Cloud Platform project with:
  - BigQuery access (read and write)
  - Secret Manager access
  - Service account credentials
- Kartverket Grunnbok API credentials:
  - Username: Stored in environment variable
  - Password/API key: Stored in Google Cloud Secret Manager

## Installation

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```env
GOOGLE_APPLICATION_CREDENTIALS_FILENAME=your-credentials-file.json
GRUNNBOK_USERNAME=your-username
```

3. Ensure Grunnbok API key is stored in Google Cloud Secret Manager under `GRUNNBOK_API_KEY`

### Docker Deployment

Build and run the Docker container:

```bash
docker build -t sibr-cadastral .
docker run sibr-cadastral --update-project --fill --transfer-type active --ownership-type eier --save
```

## Usage

### Command Line Interface

The service is executed via command line with various operation modes:

```bash
python main.py [mode] [options]
```

### Operation Modes

The service supports four mutually exclusive operation modes:

#### 1. Update Project (Recommended)
Batch process properties from BigQuery:
```bash
python main.py --update-project --fill --transfer-type active --ownership-type eier --save
```

#### 2. By Properties
Fetch data for specific properties:
```bash
python main.py --by-properties kommunenr gnr bnr festnr seksjonsnr --transfer-type active
```

#### 3. By Period
Fetch transfers within a date range:
```bash
python main.py --by-period --start-date 2024-01-01 --end-date 2024-12-31
```

#### 4. By Address
Fetch data for a single address:
```bash
python main.py --address "Karl Johans gate 1, Oslo" --section-num 1
```

### Required Parameters

When using `--update-project`, you must specify:
- **Processing Mode**: Either `--fill` or `--overwrite`
- **Save Option**: `--save` to store results in BigQuery

### Optional Parameters

- `--transfer-type <active|historical>`: Type of transfer records to fetch (default: both)
- `--ownership-type <eier|andel>`: Type of ownership (default: both)
- `--limit <number>`: Limit number of properties to process
- `--section-num <number>`: Section number for address-based queries
- `--start-date <YYYY-MM-DD>`: Start date for period queries
- `--end-date <YYYY-MM-DD>`: End date for period queries

### Examples

#### Fill Missing Active Ownership Records
```bash
python main.py --update-project --fill --transfer-type active --ownership-type eier --save
```

#### Update Recent Properties with Historical Data
```bash
python main.py --update-project --overwrite --transfer-type historical --save
```

#### Process All Types with Limit
```bash
python main.py --update-project --fill --save --limit 1000
```

#### Process Only Cooperative Housing
```bash
python main.py --update-project --fill --ownership-type andel --save
```

#### Test Specific Property
```bash
python main.py --by-properties 0301 123 456 0 0 --transfer-type active
```

## Configuration

### BigQuery Schema

The service interacts with the following BigQuery datasets and tables:

**Input Table:**
- `sibr-market.clean.homes` - Property listings with cadastral identifiers

Required columns for ownership properties (eier):
- `item_id` - Unique listing identifier
- `municipality_num` - Kommune number
- `cadastral_num` - Gaard number
- `unit_num` - Bruk number
- `leasehold_num` - Feste number (optional)
- `section_num` - Seksjon number (optional)
- `ownership_type` - Type of ownership

Required columns for cooperative housing (andel):
- `item_id` - Unique listing identifier
- `coop_unit_num` - Andel number
- `coop_org_num` - Borettslag number
- `ownership_type` - Type of ownership

**Output Table:**
- `sibr-market.staging.cadastrals` - Cadastral records with ownership and transfer data

### Batch Configuration

Configured in `main.py`:
- Batch size: 50,000 properties per batch
- Concurrent API requests: Managed by `kartverkets-api` package
- Automatic deduplication: Keeps most recent record per property

### Data Cleaning

The service automatically:
- Merges API responses with source property data
- Removes unnecessary columns and metadata
- Adds processing timestamps
- Marks records as active/historical
- Handles duplicate entries (keeps latest per property)

## Project Structure

```
cadastral/
├── main.py              # Entry point and CLI interface
├── examples.ipynb       # Usage examples and testing
├── Dockerfile           # Docker container definition
├── requirements.in      # Direct dependencies
└── requirements.txt     # Pinned dependencies
```

## Dependencies

Key dependencies include:

- **kartverkets-api** (>= 0.1.14): Kartverket Grunnbok API client
- **sibr-module** (>= 0.2.11): Internal SIBR utilities for BigQuery, logging, and secrets
- **pandas**: Data manipulation and transformation
- **aiohttp**: Async HTTP client for API requests
- **google-cloud-bigquery**: BigQuery client
- **google-cloud-secret-manager**: Secure credential storage
- **python-dotenv**: Environment configuration

## Data Flow

### Update Project Process

1. **Query Source Data**: Fetch properties from `sibr-market.clean.homes` based on filters
2. **Transform Identifiers**: Convert property identifiers to Kartverket API format
3. **Batch Processing**: Split properties into batches of 50,000
4. **API Requests**: Fetch cadastral data asynchronously from Grunnbok API
5. **Data Cleaning**: Merge responses with source data and remove unnecessary columns
6. **Save to BigQuery**: Merge results into `staging.cadastrals` table
7. **Deduplication**: Mark old records as inactive when newer records exist

### Deduplication Logic

The service automatically handles duplicate records:
- When processing active transfers, keeps only the most recent record per property
- Uses SQL MERGE operations to mark superseded records as inactive
- Ensures data integrity and prevents duplicate ownership records

## Error Handling

The service handles various error scenarios:

- **API Errors**: Logs errors and continues with remaining properties
- **Missing Data**: Gracefully handles properties with incomplete cadastral numbers
- **Batch Failures**: Isolates batch errors to prevent full process failure
- **Connection Issues**: Proper async session management and cleanup

## Logging

Comprehensive logging using `sibr-module` LoggerV2:

- Progress updates for batch processing
- Input/output counts for data cleaning steps
- API request statistics
- Error messages with context
- Execution time tracking

Log messages include:
- Batch progress (properties processed, percentage complete)
- Transfer type and ownership type being processed
- Number of records input/output from each processing step
- Total execution time

## Performance

The service is optimized for high-throughput processing:

- Asynchronous API requests via `kartverkets-api`
- Large batch sizes (50,000 properties)
- Efficient pandas operations for data transformation
- Incremental saves to BigQuery

Typical performance:
- Processing time depends on batch size and API response time
- Handles hundreds of thousands of properties in single run

## Data Quality

The service ensures data quality through:

- **Source Validation**: Only processes properties with required cadastral identifiers
- **API Response Validation**: Handled by `kartverkets-api` package
- **Duplicate Prevention**: Automatic deduplication by property ID
- **Active Status Management**: Marks superseded records as inactive
- **Timestamp Tracking**: Records when data was fetched

## Security

- **Credential Management**: API credentials stored in Google Cloud Secret Manager
- **Service Account Auth**: Google Cloud authentication via service accounts
- **Environment Isolation**: Separate configurations for local and cloud environments
- **No Sensitive Data Logging**: Credentials excluded from logs

## Limitations

- **API Rate Limits**: Subject to Kartverket Grunnbok API limitations
- **Norwegian Properties Only**: Only works for Norwegian cadastral system
- **Batch Processing**: Not designed for real-time lookups
- **Data Coverage**: Limited to what's available in Grunnbok registry

## Troubleshooting

### Common Issues

**Missing Grunnbok API Key**
```
Error: Secret not found: GRUNNBOK_API_KEY
```
Solution: Ensure API key is stored in Google Cloud Secret Manager

**BigQuery Permission Errors**
```
Error: 403 Forbidden
```
Solution: Verify service account has BigQuery read/write permissions

**No Properties Found**
```
Output: 0 properties processed
```
Solution: Check filters (fill/overwrite mode, date ranges, ownership type)

## Future Improvements

Potential enhancements:
- Real-time API endpoint for single property lookups
- Caching layer for frequently accessed properties
- Enhanced error recovery and retry logic
- Monitoring and alerting for batch jobs
- Support for additional property types
- Historical ownership change tracking

## Related Components

This cadastral component integrates with:
- **Scraping**: Provides property identifiers for cadastral lookup
- **API**: May use cadastral data for geocoding context
- **Modeling**: Uses cadastral data for property analysis
- **BigQuery**: Central data warehouse for all property data

## Legal and Compliance

- Data sourced from official Norwegian public registries (Kartverket)
- Subject to Norwegian data protection regulations
- Cadastral data is public information in Norway
- Ensure compliance with Kartverket's terms of service

## Support

For issues or questions related to the cadastral service:
- Check the `examples.ipynb` for usage examples
- Review the `kartverkets-api` package documentation
- Refer to the main project documentation
- Contact the development team
