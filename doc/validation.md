# Validation Framework

## Overview

The validation framework provides statistical rigor for backtest results through walk-forward analysis, Monte Carlo permutation testing, and deflated Sharpe ratio.

## Walk-Forward Analysis

```python
from cryptobot.backtest.validation import walk_forward_returns

# Rolling window walk-forward
splits = walk_forward_returns(
    returns=returns_series,
    n_splits=5,
    embargo=0.01,  # 1% gap between train/test
)

# Results per split
for split in splits:
    print(f"Split {split['split']}: train={split['train_size']}, test={split['test_size']}")
    print(f"  Train Sharpe: {split['train_sharpe']:.3f}")
    print(f"  Test Sharpe: {split['test_sharpe']:.3f}")
    print(f"  OOS Mean: {split['oos_mean']:.4f}")
    print(f"  OOS Std: {split['oos_std']:.4f}")
    print(f"  Stability: {split['stability']:.3f}")
```

### Configuration

```python
from cryptobot.backtest.validation import walk_forward_returns

splits = walk_forward_returns(
    returns=returns_series,
    n_splits=5,           # Number of walk-forward windows
    embargo=0.01,         # 1% gap between train/test (prevents leakage)
    min_train_size=100,   # Minimum training samples
)
```

### Output Structure

```python
{
    "splits": [
        {
            "split": 0,
            "train_size": 800,
            "test_size": 200,
            "train_sharpe": 1.5,
            "test_sharpe": 1.2,
            "oos_mean": 0.001,
            "oos_std": 0.01,
            "stability": 0.8,
        },
        ...
    ],
    "oos_mean": 0.0012,
    "oos_sharpe": 1.1,
    "oos_std": 0.009,
    "stability": 0.75,
    "passed": True
}
```

## Monte Carlo Permutation Testing

```python
from cryptobot.backtest.validation import monte_carlo_significance

result = monte_carlo_significance(
    returns=returns_series,
    n_permutations=1000,  # Number of permutations
)

print(f"P-value: {result['p_value']:.4f}")
print(f"Observed Sharpe: {result['observed_sharpe']:.3f}")
print(f"Permutations: {result['permutations']}")
print(f"Passed (p < 0.05): {result['passed']}")
```

### How It Works

1. Compute observed Sharpe ratio
2. Randomly permute returns N times
3. Compute Sharpe for each permutation
4. P-value = fraction of permutations with Sharpe >= observed
5. Passed if p-value < 0.05 AND observed Sharpe > 0

### Configuration

```python
from cryptobot.backtest.validation import monte_carlo_significance

result = monte_carlo_significance(
    returns=returns_series,
    n_permutations=1000,    # More = more precise p-value
)
```

### Output

```python
{
    "p_value": 0.023,
    "observed_sharpe": 1.45,
    "permutations": 1000,
    "permuted_sharpes": [...],  # All permutation sharpes
    "passed": True
}
```

## Deflated Sharpe Ratio

Adjusts Sharpe ratio for multiple testing (selection bias).

```python
from cryptobot.backtest.validation import deflated_sharpe

result = deflated_sharpe(
    returns=returns_series,
    n_trials=1,           # Number of strategy variants tested
    benchmark_sharpe=0.0, # Benchmark Sharpe (e.g., buy & hold)
)

print(f"Observed Sharpe: {result['observed_sharpe']:.3f}")
print(f"Expected Max Sharpe: {result['expected_max_sharpe']:.3f}")
print(f"Probabilistic Sharpe Ratio: {result['probabilistic_sharpe_ratio']:.3f}")
print(f"Deflated Sharpe: {result['deflated_sharpe']:.3f}")
print(f"Passed (PSR > 0.95): {result['passed']}")
```

### How It Works

1. Compute observed Sharpe
2. Estimate expected maximum Sharpe from n_trials
3. Compute Probabilistic Sharpe Ratio (PSR)
4. Deflated Sharpe = observed - expected_max
5. Passed if PSR > 0.95 AND deflated > 0

### Configuration

```python
from cryptobot.backtest.validation import deflated_sharpe

result = deflated_sharpe(
    returns=returns_series,
    n_trials=10,          # Number of strategy variants tested
    benchmark_sharpe=0.0, # Benchmark to beat
)
```

## Full Validation Report

```python
from cryptobot.backtest.validation import run_validation

report = run_validation(
    returns=returns_series,
    n_splits=5,           # Walk-forward splits
    n_permutations=1000,  # Monte Carlo permutations
    n_trials=1,           # Strategy variants tested
    benchmark_sharpe=0.0, # Benchmark Sharpe
)

print(f"Walk-forward passed: {report['walk_forward']['passed']}")
print(f"Monte Carlo passed: {report['monte_carlo']['passed']}")
print(f"Deflated Sharpe passed: {report['deflated_sharpe']['passed']}")
print(f"Overall passed: {report['passed']}")

# Detailed output
print(report)
```

### Complete Report Structure

```python
{
    "walk_forward": {
        "splits": [...],
        "oos_mean": 0.0012,
        "oos_sharpe": 1.1,
        "stability": 0.75,
        "passed": True
    },
    "monte_carlo": {
        "p_value": 0.023,
        "observed_sharpe": 1.45,
        "permutations": 1000,
        "passed": True
    },
    "deflated_sharpe": {
        "observed_sharpe": 1.45,
        "expected_max_sharpe": 0.8,
        "probabilistic_sharpe_ratio": 0.97,
        "deflated_sharpe": 0.65,
        "passed": True
    },
    "passed": True  # All three passed
}
```

## CLI Usage

```bash
# Run validation from CLI
python -m cryptobot.cli.main backtest \
  --strategy trend_following \
  --bars 1000 \
  --validate
```

Output:
```
Walk-Forward Validation: PASSED (stability=0.78, oos_sharpe=1.23)
Monte Carlo Significance: PASSED (p=0.012, observed_sharpe=1.34)
Deflated Sharpe: PASSED (PSR=0.96, deflated=0.58)
Overall: PASSED
```

## Interpretation Guide

| Metric | Good | Bad |
|--------|------|-----|
| Walk-forward stability | > 0.7 | < 0.5 |
| Walk-forward OOS Sharpe | > 1.0 | < 0.5 |
| Monte Carlo p-value | < 0.05 | > 0.10 |
| Probabilistic Sharpe Ratio | > 0.95 | < 0.80 |
| Deflated Sharpe | > 0 | < 0 |

## Integration with Backtest

```python
from cryptobot.backtest.data import load_bars
from cryptobot.backtest.runner import run_backtest
from cryptobot.backtest.validation import run_validation

# Run backtest
ds = load_bars(source="synthetic", symbol="BTCUSDT", timeframe="1h", n_bars=1000)
result = await run_backtest(ds.bars, strategy=strategy, symbol=ds.symbol)

# Extract returns from equity curve
equity_curve = result.equity_curve
returns = [(eq[i][1] - eq[i-1][1]) / eq[i-1][1] for i in range(1, len(eq))]

# Run validation
report = run_validation(
    returns=returns,
    n_splits=5,
    n_permutations=1000,
)

if report['passed']:
    print("Strategy PASSED validation")
else:
    print("Strategy FAILED validation")
```

## Custom Validation

```python
from cryptobot.backtest.validation import (
    walk_forward_returns,
    monte_carlo_significance,
    deflated_sharpe,
)

# Custom validation pipeline
def validate_strategy(returns, n_trials=1):
    # 1. Walk-forward
    wf = walk_forward_returns(returns, n_splits=5)
    wf_passed = wf['stability'] > 0.7 and wf['oos_sharpe'] > 1.0
    
    # 2. Monte Carlo
    mc = monte_carlo_significance(returns, n_permutations=1000)
    mc_passed = mc['passed']
    
    # 3. Deflated Sharpe
    ds = deflated_sharpe(returns, n_trials=1)
    ds_passed = ds['passed']
    
    return {
        'walk_forward': {'passed': wf_passed, 'detail': wf},
        'monte_carlo': {'passed': mc_passed, 'detail': mc},
        'deflated_sharpe': {'passed': ds_passed, 'detail': ds},
        'overall': wf_passed and mc_passed and ds_passed
    }
```

## Minimum Requirements

| Metric | Threshold |
|--------|-----------|
| Walk-forward stability | > 0.7 |
| Walk-forward OOS Sharpe | > 1.0 |
| Monte Carlo p-value | < 0.05 |
| Probabilistic Sharpe Ratio | > 0.95 |
| Deflated Sharpe | > 0 |

## Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| Look-ahead bias | Use walk-forward with embargo |
| Overfitting | Require Monte Carlo p < 0.05 |
| Multiple testing | Use deflated Sharpe |
| Data snooping | Walk-forward with embargo |
| Small sample | Minimum 200 bars |