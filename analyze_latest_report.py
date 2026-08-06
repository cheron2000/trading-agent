"""
Analyze the latest trading journal and generate a report.
"""
import json
from pathlib import Path
from datetime import datetime

# Find latest journal
journal_dir = Path("data_store/live")
journals = list(journal_dir.glob("journal-*.jsonl"))
if not journals:
    print("No journal files found!")
    exit(1)

latest = max(journals, key=lambda p: p.stat().st_mtime)
print(f"\n{'='*60}")
print(f"LATEST TRADING REPORT: {latest.name}")
print(f"{'='*60}\n")

# Read entries
entries = []
with open(latest) as f:
    for line in f:
        entries.append(json.loads(line))

print(f"📊 Total entries: {len(entries)}")

# Analyze trades
buys = [e for e in entries if e['fill']['action'] == 'BUY']
sells = [e for e in entries if e['fill']['action'] == 'SELL']

print(f"\n💰 Trading Activity:")
print(f"   BUY orders:   {len(buys)}")
print(f"   SELL orders:  {len(sells)}")
print(f"   Round trips:  {len(sells)}")

# Show first and last timestamps
if entries:
    first_time = entries[0]['timestamp']
    last_time = entries[-1]['timestamp']
    print(f"\n⏱️  Session Times:")
    print(f"   Started: {first_time}")
    print(f"   Ended:   {last_time}")

# Calculate P&L (requires matching buys/sells by symbol)
print(f"\n📈 Last 10 Trades:")
for entry in entries[-10:]:
    fill = entry['fill']
    time = fill['fill_timestamp'][11:19]
    action = fill['action']
    symbol = fill['symbol']
    price = fill['fill_price']
    qty = fill['quantity']
    
    print(f"   [{time}] {action:4} {symbol:6} @ ${price:7.2f} (qty: {qty:.6f})")

# Symbol breakdown
symbols = {}
for entry in entries:
    sym = entry['fill']['symbol']
    action = entry['fill']['action']
    if sym not in symbols:
        symbols[sym] = {'BUY': 0, 'SELL': 0}
    symbols[sym][action] += 1

print(f"\n📊 Symbol Breakdown:")
for sym, counts in sorted(symbols.items()):
    print(f"   {sym:6} - BUY: {counts['BUY']:2}, SELL: {counts['SELL']:2}")

print(f"\n{'='*60}\n")
