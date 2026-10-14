# RUN THE SWEEP — copy/paste commands

Everything below runs from the repo root: `/home/ph03n1x/trade`

---

## 1. Sanity check first (5 seconds)

```bash
cd /home/ph03n1x/trade
```

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --smoke
```

Expect this at the end:

```
MANIFEST 4 run, 0 failed
```

---

## 2. Quick pass first (recommended — ~20 min)

Small budget so you get a read fast before committing hours.

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --budget 12 --workers 8 --resume
```

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.analyze
```

Read `research/optimize/out/analyze.md`. Look at the **"beat own timing null"** row.

---

## 3. The full sweep (background, hours)

```bash
PYTHONPATH=src nohup .venv/bin/python -m research.optimize.run --budget 40 --workers 8 --resume > logs/optimize.log 2>&1 &
```

Watch it:

```bash
tail -f logs/optimize.log
```

Stop it with `Ctrl+C` — safe, finished pairs are already saved.

### Resume after stopping

Same command again:

```bash
PYTHONPATH=src nohup .venv/bin/python -m research.optimize.run --budget 40 --workers 8 --resume > logs/optimize.log 2>&1 &
```

---

## 4. Analysis (any time)

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.analyze
```

---

## 5. Send me these three

```bash
tail -100 logs/optimize.log
```

```bash
cat research/optimize/out/analyze.md
```

```bash
cat research/optimize/out/manifest.json
```

---

## Useful variations

**Only one stock:**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --stocks tcs --budget 40 --resume
```

**Only a few strategies:**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --strategies rsi_strategy supertrend_strategy donchian_channel --budget 40 --resume
```

**Pre-tax view (no capital gains tax):**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --budget 40 --no-tax --resume
```

**See what would run, without running it:**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --dry-run
```

**List all 84 strategies and their parameters:**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --list
```

**Start completely over (deletes existing results):**

```bash
PYTHONPATH=src .venv/bin/python -m research.optimize.run --budget 40 --no-resume
```

---

## If something goes wrong

**Check it is running:**

```bash
ps aux | grep research.optimize
```

**How far did it get:**

```bash
wc -l research/optimize/out/test_results.jsonl
```

Target is **4032** lines when finished.

**Check for failed pairs:**

```bash
grep -c '"ok": false' research/optimize/out/test_results.jsonl
```

**Test the harness still works:**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_nsealgo_perstock_optimizer.py -q
```

Expect `27 passed`.

---

## One thing to remember

The sweep reports **how many pairs beat their own null**, not a list of winners.

Against a null averaging **+8.59%/yr**, the best of 4,032 trials will look spectacular even
if nothing works. That is expected. Read the FDR count in `analyze.md` before believing any
pair.