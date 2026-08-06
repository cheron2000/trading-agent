"""
Check what data is currently in the dashboard state.
"""
import sys
sys.path.insert(0, "src")

from dashboard.web import dashboard_state as ds

print("="*60)
print("  Dashboard State Diagnostic")
print("="*60)

# Check portfolio state
portfolio = ds.get_portfolio()
print(f"\n📊 PORTFOLIO:")
print(f"  Cash: ${portfolio.get('cash', 0):,.2f}")
print(f"  Value: ${portfolio.get('total_value', 0):,.2f}")
print(f"  P&L: ${portfolio.get('total_pnl', 0):,.2f}")
print(f"  Positions: {len(portfolio.get('positions', []))}")

# Check open positions
positions = ds.get_positions()
print(f"\n📈 OPEN POSITIONS: {len(positions)}")
for pos in positions:
    print(f"  {pos.get('symbol', 'N/A')}: {pos.get('quantity', 0)} shares @ ${pos.get('entry_price', 0):.2f}")

# Check recent decisions
decisions = ds.get_recent_decisions()
print(f"\n🤖 RECENT DECISIONS: {len(decisions)}")
for dec in decisions[:5]:
    print(f"  {dec.get('symbol', 'N/A')}: {dec.get('action', 'N/A')} (conf: {dec.get('confidence', 0):.2f})")

# Check trade history
trades = ds.get_trade_history()
print(f"\n💰 TRADE HISTORY: {len(trades)}")
for trade in trades[:5]:
    print(f"  {trade.get('symbol', 'N/A')}: {trade.get('action', 'N/A')} {trade.get('quantity', 0)} @ ${trade.get('price', 0):.2f}")

# Check metrics
metrics = ds.get_metrics()
print(f"\n📊 METRICS:")
print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
print(f"  Total Trades: {metrics.get('total_trades', 0)}")
print(f"  Max Drawdown: {metrics.get('max_drawdown', 0):.2f}%")

# Check news
news_items = ds.get_news()
print(f"\n📰 NEWS ITEMS: {len(news_items)}")
for item in news_items[:3]:
    print(f"  {item.get('headline', 'N/A')[:60]}...")

# Check strategy mode
strategy_mode = ds.get_strategy_mode()
print(f"\n⚙️ STRATEGY MODE: {strategy_mode}")

# Check if kill switch active
kill_active = ds.is_kill_switch_active()
print(f"🛑 KILL SWITCH: {'ACTIVE' if kill_active else 'inactive'}")

print("="*60)
