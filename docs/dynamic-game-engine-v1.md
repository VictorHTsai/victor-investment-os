# Dynamic Game Engine (DGE V1)

DGE turns the “dynamic game” research framework into deterministic, auditable code.

## Design rule

DGE never claims to know a literal dealer/market-maker identity or private inventory. It estimates falsifiable latent-state probabilities from public proxies.

## Pipeline

```
Raw market / on-chain / derivatives / ETF / event data
        ↓
Provider adapters + validation + provenance
        ↓
Compression V1
        ↓
DGE feature layer: R L F C P V D E T
        ↓
DynamicGameEngine
        ↓
P(Accumulation, Test, Shakeout, Markup, Distribution, Neutral)
        ↓
Scenario / invalidator layer
        ↓
7D / 14D / 30D prediction ledger + walk-forward evaluation
```

## Factor contract

All nine factor scores are normalized to 0–100:

- R — regime / market efficiency
- L — liquidity
- F — external capital
- C — concentration/control proxy
- P — positioning / effective float pressure
- V — test-response evidence
- D — derivatives leverage/overheat
- E — abnormal-event pressure
- T — cycle prior

Raw provider values must remain available in provenance or upstream storage. Normalization rules must be versioned.

## Candidate thresholds are hypotheses

Numbers such as a 3–5% downside test, 70% four-hour reclaim, External Capital Score 75, Markup probability 60%, 14-day time stop, or 1.5% risk budget are NOT hard-coded market truths. They belong in experiment configuration and must survive walk-forward/out-of-sample tests.

## V1 acceptance

Compare:

- Baseline: Compression V1
- Experimental: Compression V1 + DGE

Measure 7/14/30D forward return, MFE, MAE, Brier score/calibration, regime-matched directional accuracy, profit factor/Sharpe after costs, and max drawdown. Use rolling feature ablation before promoting a factor into production.

## Next data-adapter work

Priority order for BTC:
1. OHLCV/Compression (existing Coinbase route)
2. spot CVD / exchange flow
3. OI / funding / liquidations
4. ETF net flow
5. stablecoin liquidity
6. on-chain STH/LTH, realized price, whale cohorts
7. event flags

Provider-specific code must live behind adapters; the DGE core remains deterministic and provider-agnostic.
