# Troubleshooting

## Common Issues

### Module Import Errors

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'cryptobot'` | Run `pip install -e .` from project root |
| `ModuleNotFoundError: No module named 'ccxt'` | Run `pip install ccxt` |
| `ModuleNotFoundError: No module named 'prometheus_client'` | Run `pip install prometheus-client` |
| `ModuleNotFoundError: No module named 'asyncpg'` | Run `pip install asyncpg` |
| `ModuleNotFoundError: No module named 'pyarrow'` | Run `pip install pyarrow` |

### Docker Issues

| Problem | Solution |
|---------|----------|
| Docker build fails | Check Dockerfile syntax, run `docker build --no-cache .` |
| `docker: command not found` | Install Docker Engine |
| `Cannot connect to Docker daemon` | Start Docker service: `sudo systemctl start docker` |
| `Permission denied` | Add user to docker group: `sudo usermod -aG docker $USER` |
| Build hangs | Try `docker build --no-cache .` |
| Multi-arch build fails | Ensure `docker buildx` is installed and QEMU is configured |

### Test Failures

| Problem | Solution |
|---------|----------|
| Tests hang | Increase timeout: `pytest --timeout=120` |
| `sqlite3` missing | Install `sqlite3` package: `apt-get install sqlite3` |
| ImportError in tests | Ensure `pip install -e .` was run |
| Async tests fail | Add `@pytest.mark.asyncio` decorator |
| Timeout in async test | Increase `--timeout=60` or use `asyncio.wait_for` |
| `asyncio.run()` in async test | Remove `asyncio.run()`, use `await` directly |

### Database Issues

| Problem | Solution |
|---------|----------|
| `sqlite3` module not found | Install Python with sqlite3 support: `apt-get install python3-sqlite3` |
| `asyncpg` connection refused | Check TimescaleDB is running and credentials |
| `timescale` loader unavailable | Install `asyncpg` and check DB connection |
| Migration failed | Run migrations manually or check schema |

### Configuration Issues

| Problem | Solution |
|---------|----------|
| Settings not loading | Check `configs/base.yaml` exists and is valid YAML |
| Environment variables not picked up | Check `.env` file or export variables |
| `pydantic` validation error | Check config types match schema |
| `extra="ignore"` swallowing errors | Temporarily set `extra="forbid"` to debug |

### Trading Issues

| Problem | Solution |
|---------|----------|
| Order rejected: "below minimum size" | Increase quantity or check `min_order_size_usd` |
| Order rejected: "above maximum size" | Reduce quantity or increase `max_order_size_usd` |
| Order rejected: "credentials missing" | Set `BINANCE_API_KEY` and `BINANCE_API_SECRET` |
| Order rejected: "kill switch active" | Check daily loss or drawdown limits |
| No fills in backtest | Check slippage/commission settings, ensure venue connected |
| Order rejected: "max drawdown exceeded" | Reduce position sizes or increase `max_drawdown_pct` |
| No fills in live trading | Check API keys, network connectivity, exchange status |

### Performance Issues

| Problem | Solution |
|---------|----------|
| Tests run slowly | Use `pytest -n auto` for parallel execution |
| Backtest slow | Reduce bars, use synthetic data, profile with `cProfile` |
| Memory leak | Check for unclosed connections, use `async with` |
| High CPU | Check for busy loops, add `await asyncio.sleep(0)` |
| Memory growth | Close DB connections, use connection pools |

### Docker Issues

| Problem | Solution |
|---------|----------|
| Build fails on `pip install` | Check `requirements.txt` for incompatible versions |
| `pip install` fails in Docker | Use `--break-system-packages` or virtual env |
| Image too large | Use multi-stage build, clean apt cache |
| Container exits immediately | Check `CMD`/`ENTRYPOINT`, ensure long-running process |
| Health check fails | Verify endpoint responds within timeout |
| Port already in use | Change port mapping: `-p 8081:8080` |

### CI/CD Issues

| Problem | Solution |
|---------|----------|
| CI fails on lint | Run `ruff check --fix src tests` locally |
| CI fails on tests | Run tests locally first |
| CI timeout | Increase timeout in workflow |
| Docker build fails in CI | Check Dockerfile syntax, base image availability |
| Cache not working | Verify cache key includes dependency hash |
| `replace()` function not found | Use matrix `include` with `tag_platform` instead of `replace()` |
| Node.js deprecation | GitHub Actions handles automatically |

### Binance API Issues

| Error | Solution |
|-------|----------|
| "Service unavailable from restricted location" | Use testnet, check IP whitelist |
| "Invalid API key" | Verify API key/secret, check permissions |
| "Signature invalid" | Check system time sync (NTP) |
| "Rate limit exceeded" | Reduce request frequency, increase `rate_limit_ms` |
| "Order would trigger immediately" | Check stop price vs market price |
| "Insufficient balance" | Check account balance, reduce quantity |

### Performance Tuning

| Issue | Optimization |
|-------|--------------|
| Slow backtest | Use synthetic data, reduce bars, disable logging |
| High memory | Use generators, close DB connections |
| Slow queries | Add indexes, use connection pooling |
| High latency | Use connection pooling, async I/O |
| High CPU | Profile with `py-spy`, optimize hot paths |

## Debugging

### Enable Debug Logging

```bash
export APP_LOG_LEVEL=DEBUG
python -m cryptobot.cli.main backtest --strategy trend_following --bars 100
```

### Debug in VS Code

```json
{
  "name": "Python: Backtest",
  "type": "python",
  "request": "launch",
  "module": "cryptobot.cli.main",
  "args": ["backtest", "--strategy", "trend_following", "--bars", "500"],
  "console": "integratedTerminal",
  "justMyCode": true
}
```

### Remote Debugging

```python
# Add to code
import debugpy
debugpy.listen(("0.0.0.0", 5678))
debugpy.wait_for_client()
```

### Profile Performance

```bash
# CPU profiling
python -m cProfile -o profile.stats -m cryptobot.cli.main backtest --strategy trend_following --bars 1000

# Analyze
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

## Logs

### Log Locations

| Source | Location |
|---------|----------|
| Application logs | Stdout/Stderr (Docker) |
| Structured logs | JSON format on stdout |
| Prometheus metrics | `/metrics` endpoint |
| Health checks | `/health` endpoint |

### Log Levels

```bash
export APP_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Log Format (JSON)

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "cryptobot.execution.engine",
  "message": "Order submitted",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 1.0,
  "order_id": "abc123",
  "correlation_id": "corr-123"
}
```

## Getting Help

1. **Check logs first** - Most issues are visible in logs
2. **Run locally first** - Reproduce locally before reporting
3. **Check GitHub Issues** - Search existing issues
4. **Create minimal repro** - Smallest code that reproduces issue
5. **Include environment** - Python version, OS, Docker version, config

### Reporting Issues

```markdown
## Bug Report

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.14
- Docker: 24.0
- Commit: abc123

**Steps to Reproduce:**
1. Run `python -m cryptobot.cli.main backtest --strategy trend_following --bars 500`
2. Observe error

**Expected:** Backtest completes
**Actual:** Error message...

**Logs:**
```
[paste relevant logs]
```
```

## Getting Help

- **GitHub Issues**: https://github.com/shobhit727/trade/issues
- **Documentation**: See `docs/` folder
- **Architecture**: See `PROJECT_MEMORY/` for design decisions