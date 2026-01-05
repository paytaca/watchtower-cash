# Stablehedge developer helper

## Overview
This document contains notes for understanding design and implementation of features in the platform.

### Aggregated Short Payout Data
The motivation is to provide minimal data to frontend(app) to calculate the estimated payout value of all short positions of a treasury contract at a given price.
```
total_short_sats = Σ(current_short_payout_estimate)
                 = Σ(nominal_units / current_price - nominal_units_at_high_liquidation)
```
The current price is unknown and changing, hence using it at server side may not give accurate data after a few minutes.

We isolate the `current_price` from the equation to allow dynamic calculation on the frontend.
```
total_short_sats = Σ(nominal_units / current_price - nominal_units_at_high_liquidation)
                 = Σ(nominal_units / current_price - nominal_units_at_high_liquidation)
                 = Σ(nominal_units / current_price) - Σ(nominal_units_at_high_liquidation)
                 = 1/current_price * Σ(nominal_units) - Σ(nominal_units_at_high_liquidation)
```

This results in only passing a fixed number of results instead of a list of values depending on number of on going short positions:
```
    total_nominal_units = Σ(nominal_units)
    total_nominal_units_at_high_liquidation = Σ(nominal_units_at_high_liquidation)
```

In the frontend:
```
    total_short_sats = (total_nominal_units / current_price) - total_nominal_units_at_high_liquidation
```
Refetching/recalculating total_short_sats on server side is no longer necessary even when `current_price` changes frequently.
