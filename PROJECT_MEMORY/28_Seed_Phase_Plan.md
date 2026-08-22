# 28 — Seed Phase Plan (v1, agreed 2026-08-22)

Mission: turn a ₹5–10k seed into a verified live track record that unlocks
family capital for the multi-exchange / multi-algorithm phase.

## Money rules

| Rule | Decision |
|---|---|
| Seed | ₹5–10k (~$60–120), Binance only at launch |
| Goal | **Two profiles raced in paper**: Realistic (beat buy&hold risk-adjusted, MDD <15%) vs Aggressive (dynamic leverage). Owner picks winner from data |
| Harvest | Every 8h: snapshot P&L → skim **10% of realized profit** → global fund |
| Global fund | Virtual sub-ledger. Draws only to keep valid open signals alive; ≤30% of fund per algo per day; frozen while kill-switch is tripped |
| Circuit breaker | −25% total equity → graceful close (capture open profit first), freeze, manual reset required |
| Leverage | Dynamic volatility-targeted inside hard bounds 0x–3x, always ≥25% price-distance from liquidation; fixed-cap variant raced against it |
| Universe | BTC + ETH only until equity grows |

## Compliance (India VDA)

- FIFO cost basis per asset; every disposal (incl. crypto→crypto) realizes gain/loss
- Tax estimate: flat 30% + 4% cess (~31.2%); only acquisition cost deductible; losses give zero relief and never carry forward (§115BBH)
- Track 1% TDS credits (§194S); international exchanges don't auto-deduct — self-report
- Export Schedule-VDA-shaped CSV for the CA to verify and file

## Autonomy & control

- Owner keeps full control rights but commits not to intervene during testing; all owner actions are logged
- 60-day paper gate: net-positive · Sharpe ≥ 1 · fills match simulation · zero breaker trips → live mode unlocked (launch confirmation line retained)
- Gate failure: auto-extend 30 days, max 2 extensions, then full strategy review with collected data

## Reporting

- English. Monthly PDF (equity curve, stats, tax estimate) + read-only dashboard link + end-of-day WhatsApp summary + major-event alerts; email carries full details
- WhatsApp via official Business Cloud API on a dedicated number
- Email via Gmail SMTP app-password

## Infrastructure

- Paper phase: owner's PC. Live phase: ~₹500/mo VPS running Docker
- Exchange-native stop-loss orders placed as backup if the host dies mid-position
- Multi-exchange support via ccxt adapter layer (Binance first)

## Build order

1. ✅ Global-fund ledger + 8h harvest cycle (`core/fund.py`, wired into `live/trader.py`; 11 unit tests)
2. ✅ ccxt multi-exchange adapter layer (`CcxtVenue` generic adapter; `build_venue(mode, exchange_id)`; BinanceVenue now a thin subclass; 18 tests)
3. ✅ Allocator / tier configuration (`core/allocator.py`: equity-tiered strategy activation, YAML-configurable, fund balance excluded from allocatable equity; 11 tests)
4. Tax engine
5. 60-day gate tracker
6. Dual risk profiles + circuit breaker
→ then 60 days paper trading on PC.

Each step ships independently, tested alone.
