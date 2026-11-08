"""Optional CuPy batch-compute backend with a tested NumPy CPU fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class ComputeInfo:
    """Runtime compute details; GPU fields remain empty on CPU-only machines."""

    backend: str
    device_name: str | None
    total_memory_bytes: int | None
    fallback_reason: str | None


class ComputeEngine:
    """Execute batched linear candidate evaluation on NumPy or optional CuPy."""

    def __init__(self, backend: str = "auto", device_id: int = 0) -> None:
        # Resolve the backend lazily so importing the research package never requires CUDA.
        if backend not in {"auto", "cpu", "numpy", "cupy"}:
            raise ValueError("backend must be 'auto', 'cpu', 'numpy', or 'cupy'")
        self._cupy: Any | None = None
        self._strict_backend = backend == "cupy"
        self._device_id = device_id
        self._fallback_reason: str | None = None
        if backend in {"auto", "cupy"}:
            self._try_cupy(required=backend == "cupy")

    def _try_cupy(self, *, required: bool) -> None:
        # Probe an actual CUDA device rather than inferring support from an NVIDIA label.
        try:
            import cupy as cp

            if cp.cuda.runtime.getDeviceCount() <= self._device_id:
                raise RuntimeError(f"CUDA device index {self._device_id} is unavailable")
            cp.cuda.Device(self._device_id).use()
            self._cupy = cp
        except Exception as exc:  # noqa: BLE001 - optional GPU stack may fail in many ways.
            self._fallback_reason = f"CuPy/CUDA unavailable: {type(exc).__name__}: {exc}"
            if required:
                raise RuntimeError(self._fallback_reason) from exc

    def _fallback_after_gpu_error(self, exc: Exception) -> None:
        # Auto mode degrades to NumPy after device/runtime failures; explicit CuPy mode fails.
        reason = f"CuPy runtime failed: {type(exc).__name__}: {exc}"
        if self._strict_backend:
            raise RuntimeError(reason) from exc
        self._cupy = None
        self._fallback_reason = reason

    @property
    def backend(self) -> str:
        """Return the active numerical backend."""
        return "cupy" if self._cupy is not None else "numpy"

    def info(self) -> ComputeInfo:
        """Return backend and device information without fabricating GPU telemetry."""
        if self._cupy is None:
            return ComputeInfo("numpy", None, None, self._fallback_reason)
        cp = self._cupy
        properties = cp.cuda.runtime.getDeviceProperties(self._device_id)
        name = properties.get("name", b"unknown")
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        memory = int(properties.get("totalGlobalMem", 0)) or None
        return ComputeInfo("cupy", str(name), memory, None)

    def batch_linear_scores(self, features: np.ndarray, population_weights: np.ndarray) -> np.ndarray:
        """Evaluate population × observations dot products with a CPU/GPU backend."""
        # Shapes are explicit: features=(observations, features), weights=(population, features).
        feature_array = np.asarray(features, dtype=np.float64)
        weight_array = np.asarray(population_weights, dtype=np.float64)
        if feature_array.ndim != 2 or weight_array.ndim != 2:
            raise ValueError("features and population_weights must both be 2D arrays")
        if feature_array.shape[1] != weight_array.shape[1]:
            raise ValueError("feature dimensions do not match population weight dimensions")
        if not np.isfinite(feature_array).all() or not np.isfinite(weight_array).all():
            raise ValueError("non-finite feature or population values are not permitted")
        if self._cupy is not None:
            # Transfer the input panel once per batch and return a contiguous host result.
            cp = self._cupy
            try:
                with cp.cuda.Device(self._device_id):
                    gpu_features = cp.asarray(feature_array)
                    gpu_weights = cp.asarray(weight_array)
                    scores = gpu_weights @ gpu_features.T
                    cp.cuda.get_current_stream().synchronize()
                    return cp.asnumpy(scores)
            except Exception as exc:  # noqa: BLE001 - device OOM/driver reset can occur after probing.
                self._fallback_after_gpu_error(exc)
        return weight_array @ feature_array.T

    def batch_dense_mlp_scores(
        self,
        features: np.ndarray,
        population_parameters: np.ndarray,
        *,
        hidden_size: int,
        output_size: int = 1,
    ) -> np.ndarray:
        """Evaluate a population of one-hidden-layer tanh networks in one batched pass.

        Parameter layout for every candidate is W1, b1, W2, b2, matching DenseMLP.
        The result shape is (population, observations, output_size).
        """
        # Validate dimensions and all weights on CPU before allocating device buffers.
        feature_array = np.asarray(features, dtype=np.float64)
        parameter_array = np.asarray(population_parameters, dtype=np.float64)
        if feature_array.ndim != 2 or parameter_array.ndim != 2:
            raise ValueError("features and population_parameters must both be 2D")
        if hidden_size < 1 or output_size < 1:
            raise ValueError("hidden_size and output_size must be positive")
        if feature_array.shape[1] < 1 or parameter_array.shape[0] < 1:
            raise ValueError("feature and population dimensions must be non-empty")
        input_size = feature_array.shape[1]
        expected = (
            input_size * hidden_size
            + hidden_size
            + hidden_size * output_size
            + output_size
        )
        if parameter_array.shape[1] != expected:
            raise ValueError(
                f"population parameter width must be {expected} for the supplied network"
            )
        if not np.isfinite(feature_array).all() or not np.isfinite(parameter_array).all():
            raise ValueError("features and network parameters must be finite")

        # One shared numerical implementation supports both NumPy and CuPy namespaces.
        def evaluate(xp: Any, x: Any, theta: Any) -> Any:
            population = theta.shape[0]
            cursor = 0
            w1_count = input_size * hidden_size
            w1 = theta[:, cursor:cursor + w1_count].reshape(
                population, input_size, hidden_size
            )
            cursor += w1_count
            b1 = theta[:, cursor:cursor + hidden_size]
            cursor += hidden_size
            w2_count = hidden_size * output_size
            w2 = theta[:, cursor:cursor + w2_count].reshape(
                population, hidden_size, output_size
            )
            cursor += w2_count
            b2 = theta[:, cursor:cursor + output_size]
            # Batched matrix multiplication matches DenseMLP's exact weight layout.
            hidden = xp.tanh(
                xp.matmul(x[None, :, :], w1) + b1[:, None, :]
            )
            return xp.tanh(xp.matmul(hidden, w2) + b2[:, None, :])

        if self._cupy is not None:
            cp = self._cupy
            try:
                with cp.cuda.Device(self._device_id):
                    x = cp.asarray(feature_array)
                    theta = cp.asarray(parameter_array)
                    output = evaluate(cp, x, theta)
                    cp.cuda.get_current_stream().synchronize()
                    return cp.asnumpy(output)
            except Exception as exc:  # noqa: BLE001 - recover from GPU runtime/OOM failures in auto mode.
                self._fallback_after_gpu_error(exc)
        output = evaluate(np, feature_array, parameter_array)
        return np.asarray(output)

    def batch_long_flat_fitness(
        self,
        features: np.ndarray,
        population_weights: np.ndarray,
        forward_returns: np.ndarray,
        *,
        threshold: float = 0.0,
        fee_bps: float = 10.0,
        periods_per_year: int = 252,
    ) -> dict[str, np.ndarray]:
        """Evaluate a population of linear long/flat policies in one batch.

        Row t features make the decision for forward_returns[t]. Entry and exit
        transitions pay one side of the declared fee rate. This is a fast research
        kernel, not an execution-realistic replacement for PortfolioSimulator.
        """
        # Validate all caller inputs on CPU before transferring any large arrays.
        feature_array = np.asarray(features, dtype=np.float64)
        weight_array = np.asarray(population_weights, dtype=np.float64)
        return_array = np.asarray(forward_returns, dtype=np.float64)
        if feature_array.ndim != 2 or weight_array.ndim != 2:
            raise ValueError("features and population_weights must both be 2D")
        if feature_array.shape[1] != weight_array.shape[1]:
            raise ValueError("feature dimensions do not match population weights")
        if return_array.ndim != 1 or len(return_array) != feature_array.shape[0]:
            raise ValueError("forward_returns must have one value per feature row")
        if not (np.isfinite(feature_array).all() and np.isfinite(weight_array).all()
                and np.isfinite(return_array).all() and np.isfinite(threshold)):
            raise ValueError("fitness inputs must be finite")
        if (return_array < -1.0).any():
            raise ValueError("forward returns cannot be below -100 percent")
        if not 0.0 <= fee_bps < 10000.0 or periods_per_year < 1:
            raise ValueError("fee_bps or periods_per_year is invalid")

        # Wrap the complete CUDA path, including allocation and synchronisation.
        try:
            # Select one numerical namespace so the same formula runs on CPU and CUDA.
            xp = self._cupy if self._cupy is not None else np
            if self._cupy is None:
                x, weights, future = feature_array, weight_array, return_array
            else:
                with self._cupy.cuda.Device(self._device_id):
                    x = self._cupy.asarray(feature_array)
                    weights = self._cupy.asarray(weight_array)
                    future = self._cupy.asarray(return_array)

            # Compute all candidate signals with one matrix multiplication.
            scores = weights @ x.T
            positions = (scores > threshold).astype(xp.float64)
            previous = xp.concatenate(
                (xp.zeros((positions.shape[0], 1), dtype=xp.float64), positions[:, :-1]),
                axis=1,
            )
            turnover = xp.abs(positions - previous)
            cost_rate = fee_bps / 10000.0
            net_returns = positions * future[None, :] - turnover * cost_rate

            # Build equity with an initial unit of capital so first-period drawdown is valid.
            equity = xp.cumprod(1.0 + net_returns, axis=1)
            equity_with_start = xp.concatenate(
                (xp.ones((equity.shape[0], 1), dtype=xp.float64), equity), axis=1
            )
            peaks = xp.maximum.accumulate(equity_with_start, axis=1)
            drawdowns = equity_with_start / xp.maximum(peaks, 1e-300) - 1.0
            total_return = equity[:, -1] - 1.0
            mean_return = xp.mean(net_returns, axis=1)
            deviation = (
                xp.std(net_returns, axis=1, ddof=1)
                if net_returns.shape[1] > 1
                else xp.zeros_like(mean_return)
            )
            sharpe = xp.where(
                deviation > 0,
                mean_return / xp.maximum(deviation, 1e-300) * xp.sqrt(periods_per_year),
                0.0,
            )
            annualised = xp.power(
                xp.maximum(1.0 + total_return, 0.0),
                periods_per_year / net_returns.shape[1],
            ) - 1.0
            max_drawdown = xp.min(drawdowns[:, 1:], axis=1)
            results = {
                "total_return": total_return,
                "annualised_return": annualised,
                "sharpe": sharpe,
                "max_drawdown": max_drawdown,
                "mean_turnover": xp.mean(turnover, axis=1),
                "trade_transitions": xp.sum(turnover, axis=1),
            }

            # Synchronise once and return host arrays so the caller can persist results.
            if self._cupy is not None:
                self._cupy.cuda.get_current_stream().synchronize()
                return {key: self._cupy.asnumpy(value) for key, value in results.items()}
            return {key: np.asarray(value) for key, value in results.items()}
        except Exception as exc:  # noqa: BLE001 - keep runtime GPU failures recoverable.
            # CPU-side input validation errors must not be hidden by backend fallback.
            if self._cupy is None:
                raise
            self._fallback_after_gpu_error(exc)
            # Auto mode has disabled CuPy; recompute the exact batch on the NumPy backend.
            return self.batch_long_flat_fitness(
                feature_array,
                weight_array,
                return_array,
                threshold=threshold,
                fee_bps=fee_bps,
                periods_per_year=periods_per_year,
            )

    def benchmark_linear_scores(
        self,
        features: np.ndarray,
        population_weights: np.ndarray,
        repeats: int = 3,
    ) -> dict[str, float | str]:
        """Measure this backend locally; results are diagnostic, not portable claims."""
        # Warm-up first, then report median wall-clock duration for comparable repeats.
        if repeats < 1:
            raise ValueError("repeats must be at least one")
        self.batch_linear_scores(features, population_weights)
        durations: list[float] = []
        for _ in range(repeats):
            start = time.perf_counter()
            self.batch_linear_scores(features, population_weights)
            durations.append(time.perf_counter() - start)
        return {"backend": self.backend, "median_seconds": float(np.median(durations)),
                "repeats": float(repeats)}
