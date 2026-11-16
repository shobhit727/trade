#!/usr/bin/env python
"""RTX 5050 GPU inventory script for the hybrid-evolution-research platform.

Run on the GPU PC (Windows), OUTSIDE the trade repo — it installs packages.

Usage (PowerShell or cmd):
    python gpu_check.py            # inventory only, no installs
    python gpu_check.py --install  # install torch (cu128) + cupy-cuda12x first
    python gpu_check.py --install --index cu126   # fallback wheel index if cu128 fails

Paste the ENTIRE stdout back to me. It fills GOAL.md §17 and decides the
CUDA backend wiring (dual-backend vs torch-only) and the F-028 chunk size.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys

LINE = "=" * 72


def section(title: str) -> None:
    print(f"\n{LINE}\n## {title}\n{LINE}")


def run(cmd: list[str], check: bool = False) -> int:
    print(f"$ {' '.join(cmd)}")
    sys.stdout.flush()
    try:
        result = subprocess.run(cmd, check=check)
    except FileNotFoundError as exc:
        print(f"NOT FOUND: {exc}")
        return 127
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    return result.returncode


def pip_install(*args: str) -> int:
    return run([sys.executable, "-m", "pip", "install", *args])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--install", action="store_true",
                        help="install torch (CUDA wheel) + cupy-cuda12x before checks")
    parser.add_argument("--index", default="cu128", choices=["cu128", "cu126"],
                        help="PyTorch CUDA wheel index (default cu128 for Blackwell)")
    args = parser.parse_args()

    section("0. HOST / PYTHON INVENTORY (no installs)")
    print(f"platform: {platform.platform()}")
    print(f"python:   {sys.version}")
    run(["nvidia-smi"])
    run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap",
         "--format=csv"])

    if args.install:
        section(f"1. INSTALL torch ({args.index} wheel — pip resolves the version)")
        rc = pip_install("torch", "--index-url",
                         f"https://download.pytorch.org/whl/{args.index}")
        if rc != 0 and args.index == "cu128":
            print("\ncu128 wheel resolution failed — retrying with cu126 ...\n")
            rc = pip_install("torch", "--index-url",
                             "https://download.pytorch.org/whl/cu126")
        section("1b. INSTALL cupy-cuda12x (non-fatal if it fails)")
        pip_install("cupy-cuda12x")

    section("2. TORCH CUDA VERIFICATION")
    code = r"""
import importlib.util, traceback
if importlib.util.find_spec("torch") is None:
    print("torch NOT INSTALLED — re-run with --install, or paste the sections above.")
else:
    try:
        import torch
        print("torch:", torch.__version__)
        print("cuda available:", torch.cuda.is_available())
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            print("device:", p.name)
            print("capability:", torch.cuda.get_device_capability(0))
            print("vram GB:", round(p.total_memory / 1e9, 2))
            print("cuda runtime version (torch):", torch.version.cuda)
            a = torch.randn(1024, 1024, device="cuda")
            b = torch.randn(1024, 1024, device="cuda")
            print("matmul ok:", bool(((a @ b).sum() != 0).item()))
            try:
                t = torch.zeros(4, device="cuda", dtype=torch.bfloat16)
                print("bf16 ok:", t.dtype == torch.bfloat16)
            except Exception as exc:
                print("bf16 FAILED:", exc)
        else:
            print("-> If nvidia-smi worked above, this is a driver/wheel mismatch.")
            print("   Paste EVERYTHING (nvidia-smi + this) and the wheel gets re-picked.")
    except Exception:
        traceback.print_exc()
        print("-> torch installed but broken; paste this traceback.")
"""
    rc = run([sys.executable, "-c", code])
    if rc != 0:
        print("(torch probe exited nonzero — see message above)")

    section("3. CUPY VERIFICATION (NVRTC must compile for sm_120)")
    code = r"""
import importlib.util, traceback
if importlib.util.find_spec("cupy") is None:
    print("cupy NOT INSTALLED (optional) — the platform CUDA backend goes torch-only.")
else:
    try:
        import cupy
        print("cupy:", cupy.__version__)
        cupy.show_config()
        a = cupy.arange(10)
        print("kernel compile ok:", (a * 2).sum().item() == 90)
    except Exception:
        traceback.print_exc()
        print("-> cupy installed but cannot target this arch: torch-only backend.")
"""
    rc = run([sys.executable, "-c", code])
    if rc != 0:
        print("(cupy probe exited nonzero — see message above)")

    section("4. DONE — paste this entire output back")
    print("Decides: GOAL.md §17 inventory, CUDA backend wiring (dual vs torch-only),")
    print("and the F-028 population-chunk size from the VRAM number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
