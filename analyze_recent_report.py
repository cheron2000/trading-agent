#!/usr/bin/env python3
import json
from datetime import datetime

file_path = 'data_store/live/journal-live-run-2026-07-29-1506.jsonl'
with open(file_path, 'r') as f:
    entries = [json.loads(line) for line in f]

# Parse trades
buy_orders = [e for e in entries if e['fill']['action'] == 'BUY']
sell_orders = [e for e in entries if e['fill']['action'] == 'SELL']

# Calculate P&L
positions = {}
total_pnl = 0
trades_pnl = []

for entry in entries:
    fill = entry['fill']
    symbol = fill['symbol']
    action = fill['action']
    quantity = fill['quantity']
    price = fill['fill_price']
    
    if action == 'BUY':
        if symbol not in positions:
            positions[symbol] = []
        positions[symbol].append({'qty': quantity, 'price': price})
    elif action == 'SELL':
        if symbol in positions and positions[symbol]:
            buy = positions[symbol].pop(0)
            pnl = (price - buy['price']) * quantity
            total_pnl += pnl
            trades_pnl.append({
                'symbol': symbol, 
                'buy_price': buy['price'], 
                'sell_price': price, 
                'qty': quantity, 
                'pnl': pnl
            })

# Calculate stats
initial_capital = 20.0
final_value = initial_capital + total_pnl
total_return = (total_pnl / initial_capital) * 100
wins = len([t for t in trades_pnl if t['pnl'] > 0])
losses = len([t for t in trades_pnl if t['pnl'] <= 0])
win_rate = (wins / len(trades_pnl) * 100) if trades_pnl else 0

# Get timestamps
start_time = datetime.fromisoformat(entries[0]['timestamp'].replace('+00:00', ''))
end_time = datetime.fromisoformat(entries[-1]['timestamp'].replace('+00:00', ''))
duration = end_time - start_time

print('=' * 60)
print('LATEST TRADING REPORT — 2026-07-29-1506')
print('=' * 60)
print(f'Started:          {start_time.strftime("%Y-%m-%d %H:%M:%S")} UTC')
print(f'Ended:            {end_time.strftime("%Y-%m-%d %H:%M:%S")} UTC')
print(f'Duration:         {int(duration.total_seconds() // 60)}m {int(duration.total_seconds() % 60)}s')
print(f'Initial capital:  ${initial_capital:12,.2f}')
print(f'Final value:      ${final_value:12,.2f}')
print(f'Total P&L:        ${total_pnl:+12,.4f}')
print(f'Total return:     {total_return:+.4f}%')
print(f'BUY orders:       {len(buy_orders)}')
print(f'SELL orders:      {len(sell_orders)}')
print(f'Round trips:      {len(trades_pnl)}')
print(f'Win rate:         {win_rate:.1f}% ({wins}W / {losses}L)')
print('=' * 60)
print()
print('TRADE DETAILS:')
print('-' * 60)
for i, trade in enumerate(trades_pnl, 1):
    sign = '+' if trade['pnl'] >= 0 else ''
    print(f"{i}. {trade['symbol']:6s} | Buy: ${trade['buy_price']:7.2f} | Sell: ${trade['sell_price']:7.2f} | Qty: {trade['qty']:.6f} | P&L: ${sign}{trade['pnl']:.4f}")
print('=' * 60)

# Show open positions
print()
print('OPEN POSITIONS:')
print('-' * 60)
if positions:
    for symbol, pos_list in positions.items():
        for pos in pos_list:
            print(f"{symbol:6s} | {pos['qty']:.6f} shares @ ${pos['price']:.2f}")
else:
    print('None')
print('=' * 60)
