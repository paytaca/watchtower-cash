# Unified Asset Price API

## Overview

The Unified Asset Price API provides a single endpoint to fetch prices for both BCH (Bitcoin Cash) and CashTokens (fungible tokens) in various currencies.

## Endpoint

```
GET /api/asset-prices/
```

## Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `assets` | string | Yes | Comma-separated list of assets. Use `BCH` for Bitcoin Cash or `ct/<category_id>` for CashTokens |
| `vs_currencies` | string | Yes | Comma-separated list of currencies (e.g., `USD`, `PHP`, `BCH`) |
| `include_calculated` | boolean | No | Include calculated token/fiat prices (default: `true`) |

## Response Format

```json
{
  "prices": [
    {
      "id": 12345,
      "asset": "BCH",
      "asset_type": "bch",
      "asset_name": "Bitcoin Cash",
      "asset_symbol": "BCH",
      "currency": "USD",
      "price_value": "350.25000000",
      "timestamp": "2025-11-02T12:34:56Z",
      "source": "coingecko"
    },
    {
      "id": 67890,
      "asset": "ct/e7d03575f896634bf89c2eb43426...",
      "asset_type": "cashtoken",
      "asset_name": "USDT",
      "asset_symbol": "USDT",
      "currency": "BCH",
      "price_value": "0.00285000",
      "timestamp": "2025-11-02T12:34:45Z",
      "source": "cauldron"
    }
  ]
}
```

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | AssetPriceLog database ID (null for constant prices like BCH/BCH) |
| `asset` | string | Asset identifier: `BCH` for Bitcoin Cash or `ct/<category_id>` for CashTokens |
| `asset_type` | string | Either `bch` or `cashtoken` |
| `asset_name` | string | Asset name (e.g., "Bitcoin Cash" for BCH, token name for tokens) |
| `asset_symbol` | string | Asset symbol (e.g., "BCH" for BCH, token symbol for tokens) |
| `currency` | string | Currency code |
| `price_value` | decimal | Price value |
| `timestamp` | datetime | Price timestamp |
| `source` | string | Price source (`coingecko`, `cauldron`, `calculated`, `constant`) |
| `source_ids` | object | Source price IDs used for calculation (only for calculated prices) |
| `calculation` | string | Calculation method (only for calculated prices) |

## Usage Examples

### 1. Get BCH price in USD

```bash
GET /api/asset-prices/?assets=BCH&vs_currencies=USD
```

**Response:**
```json
{
  "prices": [
    {
      "id": 12345,
      "asset": "BCH",
      "asset_type": "bch",
      "asset_name": "Bitcoin Cash",
      "asset_symbol": "BCH",
      "currency": "USD",
      "price_value": "350.25000000",
      "timestamp": "2025-11-02T12:34:56Z",
      "source": "coingecko"
    }
  ]
}
```

### 2. Get token price in BCH

```bash
GET /api/asset-prices/?assets=ct/e7d03575f896634bf89c...&vs_currencies=BCH
```

**Response:**
```json
{
  "prices": [
    {
      "id": 67890,
      "asset": "ct/e7d03575f896634bf89c...",
      "asset_type": "cashtoken",
      "asset_name": "USDT",
      "asset_symbol": "USDT",
      "currency": "BCH",
      "price_value": "0.00285000",
      "timestamp": "2025-11-02T12:34:45Z",
      "source": "cauldron"
    }
  ]
}
```

### 3. Get multiple assets in multiple currencies

```bash
GET /api/asset-prices/?assets=BCH,ct/e7d03575f896634bf89c...&vs_currencies=USD,PHP
```

**Response:**
```json
{
  "prices": [
    {
      "id": 12345,
      "asset": "BCH",
      "asset_type": "bch",
      "asset_name": "Bitcoin Cash",
      "asset_symbol": "BCH",
      "currency": "USD",
      "price_value": "350.25000000",
      "timestamp": "2025-11-02T12:34:56Z",
      "source": "coingecko"
    },
    {
      "id": 12346,
      "asset": "BCH",
      "asset_type": "bch",
      "asset_name": "Bitcoin Cash",
      "asset_symbol": "BCH",
      "currency": "PHP",
      "price_value": "19500.50000000",
      "timestamp": "2025-11-02T12:34:56Z",
      "source": "coingecko"
    },
    {
      "id": 98765,
      "asset": "ct/e7d03575f896634bf89c...",
      "asset_type": "cashtoken",
      "asset_name": "USDT",
      "asset_symbol": "USDT",
      "currency": "USD",
      "price_value": "0.99850000",
      "timestamp": "2025-11-02T12:34:45Z",
      "source": "calculated",
      "source_ids": {
        "token_bch_price_id": 67890,
        "bch_fiat_price_id": 12345
      },
      "calculation": "token/USD = (token/BCH) / (BCH/USD)"
    },
    {
      "id": 98766,
      "asset": "ct/e7d03575f896634bf89c...",
      "asset_type": "cashtoken",
      "asset_name": "USDT",
      "asset_symbol": "USDT",
      "currency": "PHP",
      "price_value": "55.60000000",
      "timestamp": "2025-11-02T12:34:45Z",
      "source": "calculated",
      "source_ids": {
        "token_bch_price_id": 67890,
        "bch_fiat_price_id": 12346
      },
      "calculation": "token/PHP = (token/BCH) / (BCH/PHP)"
    }
  ]
}
```

### 4. Get BCH/BCH price (constant = 1)

```bash
GET /api/asset-prices/?assets=BCH&vs_currencies=BCH
```

**Response:**
```json
{
  "prices": [
    {
      "id": null,
      "asset": "BCH",
      "asset_type": "bch",
      "asset_name": "Bitcoin Cash",
      "asset_symbol": "BCH",
      "currency": "BCH",
      "price_value": "1.00000000",
      "timestamp": "2025-11-02T12:35:00Z",
      "source": "constant"
    }
  ]
}
```

### 5. Get token price without calculated fiat prices

```bash
GET /api/asset-prices/?assets=ct/e7d03575f896634bf89c...&vs_currencies=BCH,USD&include_calculated=false
```

**Response:**
```json
{
  "prices": [
    {
      "id": 67890,
      "asset": "ct/e7d03575f896634bf89c...",
      "asset_type": "cashtoken",
      "asset_name": "USDT",
      "asset_symbol": "USDT",
      "currency": "BCH",
      "price_value": "0.00285000",
      "timestamp": "2025-11-02T12:34:45Z",
      "source": "cauldron"
    }
  ]
}
```

## Price Sources

### BCH Prices
- **Source**: CoinGecko API
- **Frequency**: Updated every 2 minutes (scheduled task)
- **Currencies**: USD, PHP, and other fiat currencies
- **Cache**: 30 seconds for USD, 5 minutes for ARS

### Token Prices
- **Source**: Cauldron Indexer API (`https://indexer.cauldron.quest/cauldron/price/`)
- **Frequency**: On-demand (fetched when needed)
- **Currency**: BCH (native)
- **Cache**: 60 seconds (±30 seconds window)

### Calculated Prices
When requesting token prices in fiat currencies:
- **Formula**: `token/FIAT = (token/BCH) / (BCH/FIAT)`
- **Storage**: Calculated prices are **saved to the database** with `source='calculated'`
- **ID**: Each calculated price gets its own ID in `AssetPriceLog`
- **Source Tracking**: The `source_ids` field contains the IDs of both source prices:
  - `token_bch_price_id`: ID of the token/BCH price from Cauldron
  - `bch_fiat_price_id`: ID of the BCH/fiat price from CoinGecko
- **Timestamp**: Uses the minimum of both source timestamps
- **Caching**: Once saved, subsequent requests return the cached calculated price
- **Updates**: Calculated prices are updated when requested with newer source data
- **Only included when**: `include_calculated=true` (default)

## Error Handling

### Missing Parameters
```json
{
  "detail": "Both assets and vs_currencies are required"
}
```

### No Price Data Available
If a price is not available, it will simply be omitted from the response. The endpoint returns whatever prices it can find.

## Comparison with Legacy Endpoints

### Legacy Endpoints (still available)

1. **BCH Prices Only**:
   ```
   GET /api/bch-prices/?currencies=USD,PHP
   ```

2. **Market Prices (CoinGecko)**:
   ```
   GET /api/market-prices/?currencies=USD&coin_ids=bitcoin-cash
   ```

### Unified Endpoint (new)

```
GET /api/asset-prices/?assets=BCH,ct/<category_id>&vs_currencies=USD,PHP
```

**Benefits of Unified Endpoint:**
- ✅ Single API call for both BCH and tokens
- ✅ Consistent response format
- ✅ Automatic calculation of token/fiat prices
- ✅ Token metadata included
- ✅ More flexible and extensible

## Implementation Details

### Code Location
- **View**: `main/views/view_asset_price_log.py` - `UnifiedAssetPriceView`
- **Serializer**: `main/serializers/serializer_asset_price_log.py` - `UnifiedAssetPriceSerializer`
- **URL**: `main/urls.py` - `/api/asset-prices/`

### Database Tables
- `main_assetpricelog` - Stores all price logs
  - BCH prices: `relative_currency='BCH'`, `currency='USD'`, etc.
  - Token prices: `currency_ft_token_id=<category>`, `relative_currency='BCH'`

### Key Functions Used
- `get_latest_bch_price(currency)` - Fetches BCH prices
- `get_ft_bch_price_log(ft_category, timestamp)` - Fetches token prices

## Future Enhancements

Potential improvements for future versions:
- Historical price data endpoint
- Price change percentages (24h, 7d)
- Market cap and volume data
- Support for price ranges/OHLC data
- WebSocket support for real-time updates

