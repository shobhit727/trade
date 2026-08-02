#!/usr/bin/env bash
# Train ML model (direction classifier)
# Usage: ./scripts/train_model.sh [model_type] [data_path]

set -euo pipefail

MODEL_TYPE="${1:-direction}"
DATA_PATH="${2:-data/btc_1h.csv}"

echo "Training $MODEL_TYPE model on $DATA_PATH..."
python3 -c "
from cryptobot.ml.training import WalkForwardTrainer
from cryptobot.ml.features import build_features
from cryptobot.backtest.data import load_bars

bars = load_bars(source='csv', path='$DATA_PATH')
features = build_features(bars)
trainer = WalkForwardTrainer()
result = trainer.train(features)
print(f'Model trained: {result.model_path}')
print(f'CV Sharpe: {result.metrics.sharpe_ratio:.2f}')
"