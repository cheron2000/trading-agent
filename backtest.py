"""
backtest.py — Historical Backtesting Framework for AI Trading OS.

Replays historical OHLCV data through FeatureEngineer and Strategy layers,
simulating trade fills with slippage & commission, and computes performance metrics.

Usage:
    python backtest.py --symbol AAPL --days 30 --strategy SIMPLE-RULE
    python backtest.py --symbol BTC-USD --days 14 --strategy SIMPLE-RULE --capital 50000
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src/ to sys.path if needed
sys.path.insert(0, str(Path(__file__).parent / "src"))

from data.features.feature_engineer import FeatureEngineer
from data.models.feature_vector import FeatureVector
from data.models.market_tick import MarketTick
from intelligence.strategies.rule_based import SimpleRuleStrategy


class SimpleBacktestEngine:
    """Historical backtesting engine for single or multi-asset strategy evaluation."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        slippage_pct: float = 0.0005,  # 0.05% slippage
        commission_per_trade: float = 0.0,  # Zero-commission default
    ) -> None:
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.commission = commission_per_trade

    def generate_synthetic_data(
        self, symbol: str, days: int = 30, interval_mins: int = 60
    ) -> list[MarketTick]:
        """Generate deterministic historical synthetic price ticks for backtesting demonstration."""
        ticks = []
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        total_steps = int((days * 24 * 60) / interval_mins)

        base_price = 150.0 if "USD" not in symbol else 60000.0
        curr_price = base_price

        for i in range(total_steps):
            ts = start + timedelta(minutes=i * interval_mins)
            # Sine wave trend + noise
            trend = math.sin(i / 10.0) * (base_price * 0.01)
            noise = math.cos(i / 3.0) * (base_price * 0.005)
            curr_price = max(1.0, curr_price + trend + noise)

            tick = MarketTick(
                symbol=symbol,
                price=round(curr_price, 2),
                volume=1000.0 + (i % 10) * 100.0,
                timestamp=ts,
                source="backtest",
            )
            ticks.append(tick)

        return ticks

    def run(self, symbol: str, ticks: list[MarketTick], strategy) -> dict:
        """Run backtest loop over tick series."""
        fe = FeatureEngineer()
        cash = self.initial_capital
        position_qty = 0.0
        entry_price = 0.0
        trades = []
        equity_curve = [self.initial_capital]
        window_ticks: list[MarketTick] = []

        for tick in ticks:
            window_ticks.append(tick)
            if len(window_ticks) > 30:
                window_ticks.pop(0)

            fv = fe.compute(window_ticks)

            current_price = tick.price
            pos_context = {
                "has_position": position_qty > 0,
                "entry_price": entry_price,
                "current_price": current_price,
                "pnl_pct": ((current_price - entry_price) / entry_price * 100.0)
                if entry_price > 0
                else 0.0,
                "hold_cycles": 1,
            }

            if hasattr(strategy, "evaluate_with_context"):
                decision = strategy.evaluate_with_context(fv, position_context=pos_context)
            else:
                decision = strategy.evaluate(fv)

            # Signal execution simulation
            if decision.action == "BUY" and position_qty == 0:
                fill_price = current_price * (1.0 + self.slippage_pct)
                buy_amount = cash * 0.95  # Allocate 95% of available cash
                position_qty = buy_amount / fill_price
                cash -= (buy_amount + self.commission)
                entry_price = fill_price
                trades.append({"type": "BUY", "price": fill_price, "time": tick.timestamp})

            elif decision.action == "SELL" and position_qty > 0:
                fill_price = current_price * (1.0 - self.slippage_pct)
                proceeds = (position_qty * fill_price) - self.commission
                pnl = proceeds - (position_qty * entry_price)
                pnl_pct = (fill_price - entry_price) / entry_price * 100.0
                cash += proceeds
                trades.append({
                    "type": "SELL",
                    "price": fill_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "time": tick.timestamp,
                })
                position_qty = 0.0
                entry_price = 0.0

            curr_equity = cash + (position_qty * current_price)
            equity_curve.append(curr_equity)

        # Final mark to market
        final_price = ticks[-1].price if ticks else 0.0
        final_equity = cash + (position_qty * final_price)
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        sell_trades = [t for t in trades if t["type"] == "SELL"]
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        win_rate = (len(winning_trades) / len(sell_trades) * 100.0) if sell_trades else 0.0

        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

        return {
            "symbol": symbol,
            "initial_capital": self.initial_capital,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "total_trades": len(trades),
            "executed_roundtrips": len(sell_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd,
        }


def main():
    parser = argparse.ArgumentParser(description="Backtesting Framework for AI Trading OS")
    parser.add_argument("--symbol", type=str, default="AAPL", help="Ticker symbol")
    parser.add_argument("--days", type=int, default=30, help="Backtest duration in days")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital in USD")
    parser.add_argument("--strategy", type=str, default="SIMPLE-RULE", help="Strategy to evaluate")
    args = parser.parse_args()

    engine = SimpleBacktestEngine(initial_capital=args.capital)
    ticks = engine.generate_synthetic_data(symbol=args.symbol, days=args.days)
    strategy = SimpleRuleStrategy(threshold=0.3)

    print("\n" + "=" * 60)
    print(f"  AI Trading OS — Historical Backtest Report ({args.symbol})")
    print("=" * 60)
    results = engine.run(symbol=args.symbol, ticks=ticks, strategy=strategy)

    print(f"  Initial Capital  : ${results['initial_capital']:,.2f}")
    print(f"  Final Equity     : ${results['final_equity']:,.2f}")
    print(f"  Total Return     : {results['total_return_pct']:+.2f}%")
    print(f"  Total Trades     : {results['total_trades']} ({results['executed_roundtrips']} round-trips)")
    print(f"  Win Rate         : {results['win_rate']:.1f}%")
    print(f"  Profit Factor    : {results['profit_factor']:.2f}")
    print(f"  Max Drawdown     : {results['max_drawdown_pct']:.2f}%")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
