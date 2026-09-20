# TradingWavesBot Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Python core — models, risk engine, journal, simulated broker, strategy registry and the 1H opening-range strategy — so the strategy can be backtested end-to-end on macOS with no MetaTrader installed.

**Architecture:** A domain core with no broker imports, surrounded by adapters behind a `BrokerPort` protocol. Phase 1 implements only the `sim_broker` adapter, which replays historical candles and simulates fills. Strategies are registered plugins returning `Signal` objects; every signal passes through one risk gate before reaching the broker.

**Tech Stack:** Python 3.11+, `pytest`, `PyYAML`, standard-library `sqlite3`. No MetaTrader dependency in this phase.

**Spec:** `docs/superpowers/specs/2026-09-20-tradingwavesbot-design.md`

## Global Constraints

- Python 3.11+ (`match`, `StrEnum`, and `datetime.UTC` are permitted).
- Nothing under `src/core/`, `src/strategies/` or `src/optimize/` may import `MetaTrader5`, perform network I/O, or read the clock directly — time always arrives as a parameter.
- All prices are `float`. All distances in configuration are expressed in **pips**; conversion to price happens through `SymbolSpec` only.
- All datetimes are timezone-aware and stored in UTC. Naive datetimes are a bug.
- Money risk is a percentage of equity. No fixed-lot code paths.
- Every rejected signal is journalled with a machine-readable `RejectCode`.
- Test suite must pass on macOS with no MT5 present.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/tradingwaves/__init__.py`
- Create: `src/tradingwaves/core/__init__.py`
- Create: `src/tradingwaves/brokers/__init__.py`
- Create: `src/tradingwaves/strategies/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: installable package `tradingwaves`; `pytest` runnable from the repo root.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
def test_package_importable():
    import tradingwaves

    assert tradingwaves.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "tradingwaves"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

```python
# src/tradingwaves/__init__.py
__version__ = "0.1.0"
```

Create empty `__init__.py` in `core/`, `brokers/`, `strategies/` and `tests/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffold tradingwaves package"
```

---

### Task 2: Core models

**Files:**
- Create: `src/tradingwaves/core/models.py`
- Test: `tests/core/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Direction(StrEnum)` — `BUY`, `SELL`
  - `class Timeframe(StrEnum)` — `M1`, `M5`, `M15`, `H1`, `H4`, `D1`
  - `class FillKind(StrEnum)` — `ENTRY`, `TAKE_PROFIT`, `STOP_LOSS`, `MANUAL_CLOSE`
  - `class RejectCode(StrEnum)` — `RANGE_TOO_SMALL`, `RANGE_TOO_WIDE`, `SPREAD_TOO_WIDE`, `LOT_BELOW_MINIMUM`, `DAILY_LOSS_CAP`, `MAX_POSITIONS`, `MAX_EXPOSURE`, `ALREADY_TRADED_TODAY`, `SETUP_EXPIRED`, `INVALID_SIGNAL`
  - `@dataclass(frozen=True) Candle(symbol: str, timeframe: Timeframe, time: datetime, open: float, high: float, low: float, close: float, volume: float)`
  - `@dataclass(frozen=True) SymbolSpec(symbol: str, pip_size: float, digits: int, min_lot: float, max_lot: float, lot_step: float, pip_value_per_lot: float)` with methods `pips_to_price(pips: float) -> float`, `price_to_pips(price_distance: float) -> float`, `round_lot(lot: float) -> float`
  - `@dataclass(frozen=True) TakeProfit(price: float, fraction: float, index: int)`
  - `@dataclass(frozen=True) Signal(symbol: str, direction: Direction, stop_loss: float, take_profits: tuple[TakeProfit, ...], source: str, created_at: datetime, entry_price: float | None = None, meta: dict = field(default_factory=dict))`
  - `@dataclass Position(ticket: int, symbol: str, direction: Direction, volume: float, entry_price: float, stop_loss: float, take_profits: tuple[TakeProfit, ...], opened_at: datetime, magic: int, remaining_volume: float, filled_tp_indexes: list[int] = field(default_factory=list))`
  - `@dataclass(frozen=True) Fill(ticket: int, time: datetime, price: float, volume: float, kind: FillKind, profit: float)`
  - `@dataclass(frozen=True) ClosePartial(volume: float)`, `@dataclass(frozen=True) ModifyStop(price: float)`, `@dataclass(frozen=True) CloseAll()` and `PositionAction = ClosePartial | ModifyStop | CloseAll`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_models.py
import pytest

from tradingwaves.core.models import SymbolSpec


@pytest.fixture
def eurusd() -> SymbolSpec:
    return SymbolSpec(
        symbol="EURUSD",
        pip_size=0.0001,
        digits=5,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        pip_value_per_lot=10.0,
    )


def test_pips_to_price(eurusd):
    assert eurusd.pips_to_price(100) == pytest.approx(0.0100)


def test_price_to_pips(eurusd):
    assert eurusd.price_to_pips(0.0035) == pytest.approx(35.0)


def test_round_lot_rounds_down_to_step(eurusd):
    assert eurusd.round_lot(0.1789) == pytest.approx(0.17)


def test_round_lot_below_minimum_returns_zero(eurusd):
    assert eurusd.round_lot(0.004) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.core.models'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/core/models.py` containing every type listed in the Interfaces block above. `round_lot` floors to `lot_step` using integer arithmetic to avoid float drift, then returns `0.0` if the result is below `min_lot` and clamps to `max_lot`:

```python
def round_lot(self, lot: float) -> float:
    steps = int((lot + 1e-9) / self.lot_step)
    rounded = round(steps * self.lot_step, 8)
    if rounded < self.min_lot:
        return 0.0
    return min(rounded, self.max_lot)
```

`pips_to_price` returns `pips * self.pip_size`; `price_to_pips` returns `price_distance / self.pip_size`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/core/models.py tests/core/test_models.py
git commit -m "feat: add core domain models and pip arithmetic"
```

---

### Task 3: Risk engine

**Files:**
- Create: `src/tradingwaves/core/risk.py`
- Test: `tests/core/test_risk.py`

**Interfaces:**
- Consumes: `SymbolSpec`, `Signal`, `Position`, `RejectCode`, `Direction` from Task 2.
- Produces:
  - `@dataclass(frozen=True) RiskLimits(risk_per_trade_pct: float = 1.0, daily_loss_cap_pct: float = 3.0, max_concurrent_positions: int = 3, max_total_exposure_pct: float = 10.0)`
  - `@dataclass(frozen=True) AccountState(equity: float, balance: float, realized_pnl_today: float)`
  - `@dataclass(frozen=True) RiskDecision(approved: bool, lot: float, reason: str | None = None, code: RejectCode | None = None)`
  - `class RiskEngine` with `__init__(self, limits: RiskLimits)` and `evaluate(self, signal: Signal, spec: SymbolSpec, account: AccountState, open_positions: list[Position]) -> RiskDecision`

Sizing formula: `lot = (equity * risk_pct / 100) / (sl_distance_pips * pip_value_per_lot)`, then `spec.round_lot(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_risk.py
from datetime import UTC, datetime

import pytest

from tradingwaves.core.models import Direction, RejectCode, Signal, SymbolSpec, TakeProfit
from tradingwaves.core.risk import AccountState, RiskEngine, RiskLimits


@pytest.fixture
def eurusd() -> SymbolSpec:
    return SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)


def make_signal(stop_loss: float, entry: float = 1.1000) -> Signal:
    return Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        stop_loss=stop_loss,
        take_profits=(TakeProfit(entry + 0.0100, 0.25, 0),),
        source="test",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        entry_price=entry,
    )


def test_sizes_position_from_percent_risk(eurusd):
    # 1% of 10_000 = $100 risk, 50-pip stop, $10/pip/lot -> 0.20 lots
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [])

    assert decision.approved is True
    assert decision.lot == pytest.approx(0.20)


def test_rejects_when_lot_rounds_below_minimum(eurusd):
    # Tiny account, very wide stop -> sub-minimum lot
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=50.0, balance=50.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.0000), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.LOT_BELOW_MINIMUM


def test_rejects_when_daily_loss_cap_breached(eurusd):
    engine = RiskEngine(RiskLimits(daily_loss_cap_pct=3.0))
    account = AccountState(equity=9_700.0, balance=10_000.0, realized_pnl_today=-310.0)

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.DAILY_LOSS_CAP


def test_rejects_when_max_positions_reached(eurusd, monkeypatch):
    engine = RiskEngine(RiskLimits(max_concurrent_positions=1))
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)
    existing = [object()]  # count is all that matters

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, existing)

    assert decision.approved is False
    assert decision.code is RejectCode.MAX_POSITIONS


def test_rejects_signal_with_zero_stop_distance(eurusd):
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.1000), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.INVALID_SIGNAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_risk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.core.risk'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/core/risk.py`. `evaluate` checks, in order: stop distance is non-zero (`INVALID_SIGNAL`), daily loss cap (`realized_pnl_today <= -balance * cap_pct / 100` → `DAILY_LOSS_CAP`), position count (`MAX_POSITIONS`), then computes the lot and rejects `LOT_BELOW_MINIMUM` when `round_lot` returns `0.0`. Exposure check sums `volume` of open positions against `max_total_exposure_pct` and returns `MAX_EXPOSURE`; positions without a `volume` attribute are skipped so the count-only test fixture stays valid.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_risk.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/core/risk.py tests/core/test_risk.py
git commit -m "feat: add percent-risk position sizing with hard caps"
```

---

### Task 4: SQLite journal

**Files:**
- Create: `src/tradingwaves/core/journal.py`
- Test: `tests/core/test_journal.py`

**Interfaces:**
- Consumes: `Signal`, `Fill`, `Position`, `RiskDecision` from Tasks 2–3.
- Produces:
  - `class Journal` with `__init__(self, db_path: str | Path)` (accepts `":memory:"`), `record_signal(signal: Signal) -> int`, `record_decision(signal_id: int, decision: RiskDecision) -> None`, `record_position(signal_id: int, position: Position) -> None`, `record_fill(fill: Fill) -> None`, `position_by_ticket(ticket: int) -> dict | None`, `rejections(limit: int = 50) -> list[dict]`, `close()`.

Schema is created on construction with `CREATE TABLE IF NOT EXISTS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_journal.py
from datetime import UTC, datetime

from tradingwaves.core.journal import Journal
from tradingwaves.core.models import Direction, RejectCode, Signal, TakeProfit
from tradingwaves.core.risk import RiskDecision


def make_signal() -> Signal:
    return Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        source="range_1h",
        created_at=datetime(2026, 9, 20, 8, tzinfo=UTC),
        entry_price=1.1000,
    )


def test_records_signal_and_returns_id():
    journal = Journal(":memory:")

    signal_id = journal.record_signal(make_signal())

    assert isinstance(signal_id, int)
    assert signal_id > 0


def test_rejection_is_retrievable_with_reason_code():
    journal = Journal(":memory:")
    signal_id = journal.record_signal(make_signal())

    journal.record_decision(
        signal_id,
        RiskDecision(False, 0.0, "range 3.0 pips below minimum", RejectCode.RANGE_TOO_SMALL),
    )

    rejections = journal.rejections()
    assert len(rejections) == 1
    assert rejections[0]["code"] == RejectCode.RANGE_TOO_SMALL.value
    assert "below minimum" in rejections[0]["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_journal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.core.journal'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/core/journal.py` with tables `signals`, `decisions`, `positions`, `fills`. Use `sqlite3.Row` as the row factory so reads return mappings. Store datetimes as ISO-8601 strings and take-profit ladders as JSON.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_journal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/core/journal.py tests/core/test_journal.py
git commit -m "feat: add SQLite journal for signals, decisions and fills"
```

---

### Task 5: BrokerPort protocol and simulated broker

**Files:**
- Create: `src/tradingwaves/brokers/base.py`
- Create: `src/tradingwaves/brokers/sim_broker.py`
- Test: `tests/brokers/test_sim_broker.py`

**Interfaces:**
- Consumes: `Candle`, `SymbolSpec`, `Position`, `Fill`, `Direction`, `TakeProfit`, `FillKind`, `Timeframe` from Task 2.
- Produces:
  - `class BrokerPort(Protocol)` with `account_equity() -> float`, `symbol_spec(symbol: str) -> SymbolSpec`, `current_spread_pips(symbol: str) -> float`, `get_candles(symbol: str, timeframe: Timeframe, count: int) -> list[Candle]`, `open_position(symbol: str, direction: Direction, volume: float, stop_loss: float, take_profits: tuple[TakeProfit, ...], magic: int) -> Position`, `close_partial(ticket: int, volume: float) -> Fill`, `modify_stop(ticket: int, price: float) -> None`, `open_positions() -> list[Position]`
  - `class SimBroker(BrokerPort)` with `__init__(self, candles: list[Candle], spec: SymbolSpec, starting_equity: float = 10_000.0, spread_pips: float = 1.0)`, plus `advance() -> Candle | None` which steps one candle forward and returns it, and `current_time` / `equity` properties.

`SimBroker.advance()` processes the new candle against open positions before returning it: stop-loss touches close the whole position, take-profit touches close that level's fraction. Within one candle, the stop is evaluated **before** take-profits — the pessimistic assumption, so backtests do not flatter themselves.

- [ ] **Step 1: Write the failing test**

```python
# tests/brokers/test_sim_broker.py
from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.brokers.sim_broker import SimBroker
from tradingwaves.core.models import Candle, Direction, FillKind, SymbolSpec, TakeProfit, Timeframe

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
START = datetime(2026, 9, 20, 8, tzinfo=UTC)


def candle(index: int, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        time=START + timedelta(hours=index),
        open=1.1000,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def test_advance_returns_candles_in_order():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1005), candle(1, 1.1020, 1.1000, 1.1015)], SPEC)

    first = broker.advance()
    second = broker.advance()

    assert first.time < second.time
    assert broker.advance() is None


def test_take_profit_closes_only_its_fraction():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1150, 1.1000, 1.1140)], SPEC)
    broker.advance()
    position = broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0), TakeProfit(1.1200, 0.25, 1)),
        magic=1,
    )

    broker.advance()

    assert position.remaining_volume == pytest.approx(0.30)
    assert position.filled_tp_indexes == [0]


def test_stop_loss_closes_whole_position():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1010, 1.0940, 1.0945)], SPEC)
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        magic=1,
    )

    broker.advance()

    assert broker.open_positions() == []


def test_stop_is_evaluated_before_take_profit_within_one_candle():
    # Candle touches both the TP above and the stop below; the stop must win.
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1150, 1.0940, 1.1000)], SPEC)
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        magic=1,
    )

    broker.advance()

    assert broker.open_positions() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/brokers/test_sim_broker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.brokers.sim_broker'`

- [ ] **Step 3: Write minimal implementation**

Create `base.py` with the `BrokerPort` protocol (`@runtime_checkable`), then `sim_broker.py`. Track an index into the candle list, a ticket counter, a list of open `Position` objects and a list of `Fill` records. Entry fills use the next candle's open plus half the spread for buys, minus half for sells. Profit on a fill is `(exit - entry) * volume * pip_value_per_lot / pip_size` with the sign flipped for sells.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/brokers/test_sim_broker.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/brokers tests/brokers
git commit -m "feat: add BrokerPort protocol and simulated broker"
```

---

### Task 6: Strategy protocol and registry

**Files:**
- Create: `src/tradingwaves/strategies/base.py`
- Test: `tests/strategies/test_registry.py`

**Interfaces:**
- Consumes: `Candle`, `Signal`, `Position`, `PositionAction`, `SymbolSpec`, `Timeframe` from Task 2.
- Produces:
  - `@dataclass(frozen=True) StrategyContext(spec: SymbolSpec, now: datetime, spread_pips: float, equity: float)`
  - `class Strategy(Protocol)` with `name: str`, `required_timeframes() -> list[Timeframe]`, `on_candle(candle: Candle, ctx: StrategyContext) -> Signal | None`, `on_position_update(position: Position, candle: Candle, ctx: StrategyContext) -> list[PositionAction]`
  - `register_strategy(name: str)` decorator, `get_strategy(name: str) -> type`, `available_strategies() -> list[str]`
  - `class UnknownStrategyError(KeyError)`

- [ ] **Step 1: Write the failing test**

```python
# tests/strategies/test_registry.py
import pytest

from tradingwaves.strategies.base import (
    UnknownStrategyError,
    available_strategies,
    get_strategy,
    register_strategy,
)


def test_registered_strategy_is_retrievable_by_name():
    @register_strategy("dummy_for_test")
    class Dummy:
        name = "dummy_for_test"

    assert get_strategy("dummy_for_test") is Dummy
    assert "dummy_for_test" in available_strategies()


def test_unknown_strategy_raises():
    with pytest.raises(UnknownStrategyError):
        get_strategy("no_such_strategy")


def test_duplicate_registration_raises():
    @register_strategy("dupe_for_test")
    class First:
        name = "dupe_for_test"

    with pytest.raises(ValueError):

        @register_strategy("dupe_for_test")
        class Second:
            name = "dupe_for_test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/strategies/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.strategies.base'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/strategies/base.py` with a module-level `_REGISTRY: dict[str, type]`. `register_strategy` raises `ValueError` on a duplicate name so a typo cannot silently shadow an existing strategy.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/strategies/test_registry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/strategies/base.py tests/strategies/test_registry.py
git commit -m "feat: add strategy protocol and plugin registry"
```

---

### Task 7: Range1H — range marking and entry confirmation

**Files:**
- Create: `src/tradingwaves/strategies/range_1h.py`
- Test: `tests/strategies/test_range_1h_entry.py`

**Interfaces:**
- Consumes: everything from Tasks 2 and 6.
- Produces:
  - `@dataclass(frozen=True) Range1HConfig(session_hour: int = 8, session_timezone: str = "Europe/London", confirmation_window: int = 3, tp_pips: tuple[float, ...] = (100.0, 200.0, 300.0, 400.0), sl_buffer_pips: float = 2.0, min_range_pips: float = 5.0, max_range_pips: float = 60.0, max_spread_pips: float = 3.0)`
  - `class Range1H(Strategy)` registered as `"range_1h"`, `__init__(self, config: Range1HConfig)`
  - `class SetupState(StrEnum)` — `IDLE`, `RANGE_MARKED`, `TRADED`, `ABANDONED`

Behaviour: the candle whose session-local hour equals `session_hour` marks the range and sets state `RANGE_MARKED`. Each subsequent candle is a confirmation candidate — close above range high emits a BUY `Signal`, close below range low emits a SELL. A close inside the range consumes one of `confirmation_window` attempts; exhausting them sets `ABANDONED`. State resets to `IDLE` at the next session-local day boundary.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategies/test_range_1h_entry.py
from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.core.models import Candle, Direction, SymbolSpec, Timeframe
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
# 08:00 Europe/London in September is 07:00 UTC (BST = UTC+1).
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)


def candle(hours: int, high: float, low: float, close: float) -> Candle:
    return Candle("EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), 1.1000, high, low, close, 100.0)


def ctx(candle_time: datetime, spread: float = 1.0) -> StrategyContext:
    return StrategyContext(spec=SPEC, now=candle_time, spread_pips=spread, equity=10_000.0)


def feed(strategy: Range1H, candles: list[Candle]):
    signals = []
    for c in candles:
        signals.append(strategy.on_candle(c, ctx(c.time)))
    return signals


def test_range_candle_alone_emits_no_signal():
    strategy = Range1H(Range1HConfig())

    signal = strategy.on_candle(candle(0, 1.1030, 1.1000, 1.1020), ctx(SESSION_UTC))

    assert signal is None


def test_close_above_range_high_emits_buy_with_range_low_stop():
    strategy = Range1H(Range1HConfig(sl_buffer_pips=2.0))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    signal = signals[1]
    assert signal is not None
    assert signal.direction is Direction.BUY
    # range low 1.1000 minus 2-pip buffer
    assert signal.stop_loss == pytest.approx(1.0998)
    assert len(signal.take_profits) == 4


def test_close_below_range_low_emits_sell_with_range_high_stop():
    strategy = Range1H(Range1HConfig(sl_buffer_pips=2.0))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1025, 1.0980, 1.0990)])

    signal = signals[1]
    assert signal is not None
    assert signal.direction is Direction.SELL
    assert signal.stop_loss == pytest.approx(1.1032)


def test_close_inside_range_waits_then_abandons_after_window():
    strategy = Range1H(Range1HConfig(confirmation_window=2))

    signals = feed(
        strategy,
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1028, 1.1005, 1.1010),  # inside, attempt 1
            candle(2, 1.1029, 1.1002, 1.1015),  # inside, attempt 2
            candle(3, 1.1060, 1.1030, 1.1055),  # breakout, but window exhausted
        ],
    )

    assert signals[1] is None
    assert signals[2] is None
    assert signals[3] is None


def test_only_one_trade_per_day():
    strategy = Range1H(Range1HConfig())

    signals = feed(
        strategy,
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),  # breakout -> signal
            candle(2, 1.1070, 1.1045, 1.1065),  # further breakout -> no second signal
        ],
    )

    assert signals[1] is not None
    assert signals[2] is None


def test_take_profit_ladder_uses_configured_pip_distances():
    strategy = Range1H(Range1HConfig(tp_pips=(100.0, 200.0, 300.0, 400.0)))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    tps = signals[1].take_profits
    assert [tp.price for tp in tps] == pytest.approx([1.1145, 1.1245, 1.1345, 1.1445])
    assert [tp.fraction for tp in tps] == pytest.approx([0.25, 0.25, 0.25, 0.25])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/strategies/test_range_1h_entry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.strategies.range_1h'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/strategies/range_1h.py`. Convert each candle's UTC time into `session_timezone` with `zoneinfo.ZoneInfo` to identify the session candle and the day boundary. Take-profit prices are measured from the confirmation candle's close (the expected entry), so the ladder in the test starts at `1.1045 + 0.0100`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/strategies/test_range_1h_entry.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/strategies/range_1h.py tests/strategies/test_range_1h_entry.py
git commit -m "feat: add 1H opening-range entry detection"
```

---

### Task 8: Range1H — guards and ladder feasibility

**Files:**
- Modify: `src/tradingwaves/strategies/range_1h.py`
- Create: `src/tradingwaves/core/ladder.py`
- Test: `tests/strategies/test_range_1h_guards.py`
- Test: `tests/core/test_ladder.py`

**Interfaces:**
- Consumes: Tasks 2 and 7.
- Produces:
  - `build_ladder(lot: float, tp_prices: list[float], spec: SymbolSpec) -> tuple[TakeProfit, ...]` in `core/ladder.py` — splits `lot` across as many of `tp_prices` as the lot step allows, keeping the nearest levels and dropping the furthest. Returns an empty tuple when `lot` is below `spec.min_lot`.
  - `Range1H.on_candle` returns `None` and records `last_reject: tuple[RejectCode, str] | None` when a guard vetoes.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ladder.py
import pytest

from tradingwaves.core.ladder import build_ladder
from tradingwaves.core.models import SymbolSpec

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
PRICES = [1.1100, 1.1200, 1.1300, 1.1400]


def test_full_ladder_splits_evenly():
    ladder = build_ladder(0.40, PRICES, SPEC)

    assert len(ladder) == 4
    assert sum(tp.fraction for tp in ladder) == pytest.approx(1.0)


def test_small_lot_keeps_nearest_levels_and_drops_furthest():
    ladder = build_ladder(0.03, PRICES, SPEC)

    assert [tp.price for tp in ladder] == pytest.approx([1.1100, 1.1200, 1.1300])
    assert [tp.index for tp in ladder] == [0, 1, 2]


def test_minimum_lot_collapses_to_single_target():
    ladder = build_ladder(0.01, PRICES, SPEC)

    assert len(ladder) == 1
    assert ladder[0].price == pytest.approx(1.1100)
    assert ladder[0].fraction == pytest.approx(1.0)


def test_sub_minimum_lot_yields_empty_ladder():
    assert build_ladder(0.004, PRICES, SPEC) == ()
```

```python
# tests/strategies/test_range_1h_guards.py
from datetime import UTC, datetime, timedelta

from tradingwaves.core.models import Candle, RejectCode, SymbolSpec, Timeframe
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)


def candle(hours: int, high: float, low: float, close: float) -> Candle:
    return Candle("EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), 1.1000, high, low, close, 100.0)


def ctx(t: datetime, spread: float = 1.0) -> StrategyContext:
    return StrategyContext(spec=SPEC, now=t, spread_pips=spread, equity=10_000.0)


def test_range_below_minimum_is_rejected():
    strategy = Range1H(Range1HConfig(min_range_pips=5.0))

    strategy.on_candle(candle(0, 1.1003, 1.1000, 1.1002), ctx(SESSION_UTC))  # 3-pip range
    signal = strategy.on_candle(candle(1, 1.1010, 1.1004, 1.1008), ctx(SESSION_UTC + timedelta(hours=1)))

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.RANGE_TOO_SMALL


def test_range_above_maximum_is_rejected():
    strategy = Range1H(Range1HConfig(max_range_pips=60.0))

    strategy.on_candle(candle(0, 1.1100, 1.1000, 1.1050), ctx(SESSION_UTC))  # 100-pip range
    signal = strategy.on_candle(candle(1, 1.1150, 1.1090, 1.1140), ctx(SESSION_UTC + timedelta(hours=1)))

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.RANGE_TOO_WIDE


def test_wide_spread_is_rejected():
    strategy = Range1H(Range1HConfig(max_spread_pips=3.0))

    strategy.on_candle(candle(0, 1.1030, 1.1000, 1.1020), ctx(SESSION_UTC))
    signal = strategy.on_candle(
        candle(1, 1.1050, 1.1025, 1.1045), ctx(SESSION_UTC + timedelta(hours=1), spread=9.0)
    )

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.SPREAD_TOO_WIDE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_ladder.py tests/strategies/test_range_1h_guards.py -v`
Expected: FAIL — `ModuleNotFoundError` for `ladder`, `AttributeError` for `last_reject`

- [ ] **Step 3: Write minimal implementation**

Create `core/ladder.py`. Compute `max_levels = int(lot / spec.min_lot)` capped at `len(tp_prices)`; slice `tp_prices[:max_levels]`; divide `lot` evenly across them, rounding each slice to `lot_step` and giving any remainder to the final level so the fractions sum to exactly 1.0. Add the three guard checks to `Range1H.on_candle` before it emits a signal, setting `self.last_reject`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_ladder.py tests/strategies/test_range_1h_guards.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/core/ladder.py src/tradingwaves/strategies/range_1h.py tests/core/test_ladder.py tests/strategies/test_range_1h_guards.py
git commit -m "feat: add range guards and take-profit ladder feasibility"
```

---

### Task 9: Range1H — breakeven stop management

**Files:**
- Modify: `src/tradingwaves/strategies/range_1h.py`
- Test: `tests/strategies/test_range_1h_management.py`

**Interfaces:**
- Consumes: Tasks 2, 7, 8.
- Produces: `Range1H.on_position_update(position, candle, ctx) -> list[PositionAction]` returning `[ModifyStop(entry_price)]` exactly once, after the first take-profit has filled and while `breakeven_after_tp1` is enabled. `Range1HConfig` gains `breakeven_after_tp1: bool = True`.

- [ ] **Step 1: Write the failing test**

```python
# tests/strategies/test_range_1h_management.py
from datetime import UTC, datetime

from tradingwaves.core.models import (
    Candle,
    Direction,
    ModifyStop,
    Position,
    SymbolSpec,
    TakeProfit,
    Timeframe,
)
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)


def position(filled: list[int]) -> Position:
    return Position(
        ticket=1,
        symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.40,
        entry_price=1.1045,
        stop_loss=1.0998,
        take_profits=(TakeProfit(1.1145, 0.25, 0), TakeProfit(1.1245, 0.25, 1)),
        opened_at=NOW,
        magic=1,
        remaining_volume=0.40 - 0.10 * len(filled),
        filled_tp_indexes=list(filled),
    )


def bar() -> Candle:
    return Candle("EURUSD", Timeframe.H1, NOW, 1.1100, 1.1150, 1.1090, 1.1140, 100.0)


def ctx() -> StrategyContext:
    return StrategyContext(spec=SPEC, now=NOW, spread_pips=1.0, equity=10_000.0)


def test_no_action_before_first_take_profit():
    strategy = Range1H(Range1HConfig())

    assert strategy.on_position_update(position([]), bar(), ctx()) == []


def test_stop_moves_to_breakeven_after_first_take_profit():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))

    actions = strategy.on_position_update(position([0]), bar(), ctx())

    assert actions == [ModifyStop(1.1045)]


def test_breakeven_move_is_not_repeated():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))
    pos = position([0])
    strategy.on_position_update(pos, bar(), ctx())
    pos.stop_loss = 1.1045

    assert strategy.on_position_update(pos, bar(), ctx()) == []


def test_breakeven_disabled_does_nothing():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=False))

    assert strategy.on_position_update(position([0]), bar(), ctx()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/strategies/test_range_1h_management.py -v`
Expected: FAIL with `AttributeError` or an empty-list return

- [ ] **Step 3: Write minimal implementation**

Implement `on_position_update`. Guard against repetition by comparing `position.stop_loss` to `position.entry_price` — if the stop already sits at or beyond entry in the direction of profit, return `[]`. This keeps the check stateless, so it survives a restart.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/strategies/test_range_1h_management.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/strategies/range_1h.py tests/strategies/test_range_1h_management.py
git commit -m "feat: move stop to breakeven after first take-profit"
```

---

### Task 10: Engine orchestration

**Files:**
- Create: `src/tradingwaves/core/engine.py`
- Test: `tests/core/test_engine.py`

**Interfaces:**
- Consumes: Tasks 2–9.
- Produces:
  - `class Engine` with `__init__(self, broker: BrokerPort, strategy: Strategy, risk: RiskEngine, journal: Journal, magic: int = 770001)`
  - `process_candle(candle: Candle) -> None` — manages open positions first, then evaluates the strategy for new signals, sizes them through `RiskEngine`, builds the ladder, opens the position and journals every outcome.
  - `reconcile() -> list[Position]` — queries `broker.open_positions()`, matches against journal records by ticket, adopts matches into `self.positions` and logs unmatched broker positions without adopting them.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_engine.py
from datetime import UTC, datetime, timedelta

from tradingwaves.brokers.sim_broker import SimBroker
from tradingwaves.core.engine import Engine
from tradingwaves.core.journal import Journal
from tradingwaves.core.models import Candle, Direction, SymbolSpec, TakeProfit, Timeframe
from tradingwaves.core.risk import RiskEngine, RiskLimits
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)


def candle(hours: int, high: float, low: float, close: float) -> Candle:
    return Candle("EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), 1.1000, high, low, close, 100.0)


def build(candles):
    broker = SimBroker(candles, SPEC, starting_equity=10_000.0)
    engine = Engine(
        broker=broker,
        strategy=Range1H(Range1HConfig()),
        risk=RiskEngine(RiskLimits()),
        journal=Journal(":memory:"),
    )
    return broker, engine


def test_breakout_opens_a_sized_position():
    candles = [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)]
    broker, engine = build(candles)

    while (c := broker.advance()) is not None:
        engine.process_candle(c)

    positions = broker.open_positions()
    assert len(positions) == 1
    assert positions[0].direction is Direction.BUY
    assert positions[0].volume > 0


def test_rejected_signal_is_journalled_and_opens_nothing():
    # 3-pip range trips min_range_pips
    candles = [candle(0, 1.1003, 1.1000, 1.1002), candle(1, 1.1012, 1.1004, 1.1010)]
    broker, engine = build(candles)

    while (c := broker.advance()) is not None:
        engine.process_candle(c)

    assert broker.open_positions() == []
    assert len(engine.journal.rejections()) >= 1


def test_reconcile_ignores_positions_not_in_journal():
    broker, engine = build([candle(0, 1.1030, 1.1000, 1.1020)])
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.10,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 1.0, 0),),
        magic=999999,  # not ours
    )

    adopted = engine.reconcile()

    assert adopted == []
    assert len(broker.open_positions()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.core.engine'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/core/engine.py`. `process_candle` first calls `strategy.on_position_update` for each tracked position and applies returned actions via the broker, then calls `strategy.on_candle`. When a signal arrives it records the signal, evaluates risk, records the decision, and on approval builds the ladder with `build_ladder` and calls `broker.open_position`. When the strategy itself vetoed, read `strategy.last_reject` and journal it as a rejection.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_engine.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/core/engine.py tests/core/test_engine.py
git commit -m "feat: add engine orchestration and position reconciliation"
```

---

### Task 11: Configuration loading

**Files:**
- Create: `src/tradingwaves/config.py`
- Create: `config/settings.yaml`
- Create: `config/symbols.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `SymbolSpec`, `RiskLimits`, `Range1HConfig`.
- Produces:
  - `@dataclass(frozen=True) Settings(broker: str, magic: int, symbols: list[str], strategy: str, risk: RiskLimits, strategy_config: dict)`
  - `load_settings(path: str | Path) -> Settings`
  - `load_symbol_specs(path: str | Path) -> dict[str, SymbolSpec]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from tradingwaves.config import load_settings, load_symbol_specs


def test_loads_settings(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        """
broker: sim
magic: 770001
strategy: range_1h
symbols: [EURUSD, GBPUSD]
risk:
  risk_per_trade_pct: 1.0
  daily_loss_cap_pct: 3.0
  max_concurrent_positions: 3
  max_total_exposure_pct: 10.0
strategy_config:
  session_hour: 8
  session_timezone: Europe/London
""".strip()
    )

    settings = load_settings(path)

    assert settings.broker == "sim"
    assert settings.symbols == ["EURUSD", "GBPUSD"]
    assert settings.risk.risk_per_trade_pct == 1.0
    assert settings.strategy_config["session_hour"] == 8


def test_loads_symbol_specs(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text(
        """
EURUSD:
  pip_size: 0.0001
  digits: 5
  min_lot: 0.01
  max_lot: 100.0
  lot_step: 0.01
  pip_value_per_lot: 10.0
""".strip()
    )

    specs = load_symbol_specs(path)

    assert specs["EURUSD"].pip_size == 0.0001
    assert specs["EURUSD"].pips_to_price(10) == 0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradingwaves.config'`

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingwaves/config.py` using `yaml.safe_load`. Write the real `config/settings.yaml` and `config/symbols.yaml` with EURUSD, GBPUSD, USDJPY (note `pip_size: 0.01`, `digits: 3` for JPY pairs) and AUDUSD.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/config.py config tests/test_config.py
git commit -m "feat: add YAML configuration loading"
```

---

### Task 12: Backtest runner and CSV data loading

**Files:**
- Create: `src/tradingwaves/data/csv_loader.py`
- Create: `src/tradingwaves/core/metrics.py`
- Create: `scripts/backtest.py`
- Test: `tests/data/test_csv_loader.py`
- Test: `tests/core/test_metrics.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `load_candles_csv(path: str | Path, symbol: str, timeframe: Timeframe) -> list[Candle]` — reads columns `time,open,high,low,close,volume`, parses `time` as ISO-8601 and attaches UTC when the value is naive.
  - `@dataclass(frozen=True) BacktestMetrics(trades: int, wins: int, losses: int, win_rate: float, gross_profit: float, gross_loss: float, profit_factor: float, net_profit: float, max_drawdown: float, expectancy: float)`
  - `compute_metrics(fills: list[Fill], starting_equity: float) -> BacktestMetrics`
  - `scripts/backtest.py` — CLI: `python scripts/backtest.py --csv data/EURUSD_H1.csv --symbol EURUSD --settings config/settings.yaml`, printing the metrics table.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_csv_loader.py
from datetime import UTC

from tradingwaves.core.models import Timeframe
from tradingwaves.data.csv_loader import load_candles_csv


def test_loads_candles_with_utc_times(tmp_path):
    path = tmp_path / "EURUSD_H1.csv"
    path.write_text(
        "time,open,high,low,close,volume\n"
        "2026-09-21T07:00:00,1.1000,1.1030,1.1000,1.1020,100\n"
        "2026-09-21T08:00:00,1.1020,1.1050,1.1025,1.1045,120\n"
    )

    candles = load_candles_csv(path, "EURUSD", Timeframe.H1)

    assert len(candles) == 2
    assert candles[0].time.tzinfo is UTC
    assert candles[1].close == 1.1045
```

```python
# tests/core/test_metrics.py
from datetime import UTC, datetime

import pytest

from tradingwaves.core.metrics import compute_metrics
from tradingwaves.core.models import Fill, FillKind

NOW = datetime(2026, 9, 21, tzinfo=UTC)


def fill(profit: float, kind: FillKind = FillKind.TAKE_PROFIT) -> Fill:
    return Fill(ticket=1, time=NOW, price=1.1, volume=0.1, kind=kind, profit=profit)


def test_metrics_over_mixed_results():
    fills = [fill(100.0), fill(-50.0, FillKind.STOP_LOSS), fill(200.0)]

    m = compute_metrics(fills, starting_equity=10_000.0)

    assert m.trades == 3
    assert m.wins == 2
    assert m.net_profit == pytest.approx(250.0)
    assert m.profit_factor == pytest.approx(6.0)
    assert m.win_rate == pytest.approx(2 / 3)


def test_no_fills_yields_zeroed_metrics():
    m = compute_metrics([], starting_equity=10_000.0)

    assert m.trades == 0
    assert m.profit_factor == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_csv_loader.py tests/core/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError` for both modules

- [ ] **Step 3: Write minimal implementation**

Create both modules. `compute_metrics` walks fills in time order accumulating equity to find max drawdown; `profit_factor` is `gross_profit / abs(gross_loss)`, returning `0.0` when there are no fills and `float("inf")` when there are wins but no losses. Then write `scripts/backtest.py` wiring `load_candles_csv` → `SimBroker` → `Engine` → `compute_metrics`, printing the result.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -v`
Expected: PASS — the entire suite

- [ ] **Step 5: Commit**

```bash
git add src/tradingwaves/data src/tradingwaves/core/metrics.py scripts/backtest.py tests/data tests/core/test_metrics.py
git commit -m "feat: add CSV loading, backtest metrics and runner script"
```

---

## Phase 1 exit criteria

- `python -m pytest` passes on macOS with no MetaTrader installed.
- `python scripts/backtest.py --csv <file> --symbol EURUSD` produces a metrics table from real historical candles.
- Adding a second strategy requires creating one file under `src/tradingwaves/strategies/` and changing one line of `config/settings.yaml`.
