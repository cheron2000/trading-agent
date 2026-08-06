# Telegram Bot Setup Guide

**Required for:** Using `run_hour.py --telegram` flag

---

## Step 1: Create a Telegram Bot

1. **Open Telegram** on your phone or computer
2. **Search for:** `@BotFather` (official Telegram bot creator)
3. **Start a chat** and send: `/newbot`
4. **Follow the prompts:**
   - Enter a name for your bot (e.g., "My Trading Bot")
   - Enter a username ending in "bot" (e.g., "my_trading_alert_bot")

5. **Save the token** — BotFather will reply with:
   ```
   Done! Your bot is @my_trading_alert_bot
   Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

---

## Step 2: Get Your Chat ID

**Option A: Use @userinfobot (Easiest)**
1. Search for `@userinfobot` in Telegram
2. Start a chat with it
3. Send any message
4. It will reply with your user ID (e.g., `987654321`)
5. This is your `TELEGRAM_CHAT_ID`

**Option B: Use @RawDataBot**
1. Search for `@RawDataBot` in Telegram
2. Start a chat and send any message
3. Look for `"id":` in the JSON response
4. Copy the number (e.g., `987654321`)

---

## Step 3: Add Credentials to keys.env

Open `keys.env` in your project root and add:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321
```

**Replace with your actual values!**

---

## Step 4: Test Your Bot

Start the bot to receive your first message:

1. **Start your trading bot:**
   ```bash
   py -3 run_hour.py --telegram --minutes 5
   ```

2. **Open Telegram** and search for your bot (`@my_trading_alert_bot`)
3. **Send:** `/status`
4. **You should get a reply:**
   ```
   📈 Portfolio Status
   Value: 100000.00
   Cash:  100000.00
   ```

---

## Available Bot Commands

Once running, you can control your trading system from your phone:

| Command | Description |
|---------|-------------|
| `/status` | Portfolio value and cash balance |
| `/positions` | List of open positions |
| `/pnl` | Realized P&L and total return |
| `/stop` | Graceful system shutdown |

---

## Notifications You'll Receive

The bot automatically sends:

✅ **Trade Fills** — Every buy/sell with P&L
```
✅ Trade Fill — SELL
Symbol:    BTC-USD
Qty:       0.0500
Price:     62500.00
Time:      2026-08-06T10:30:00+00:00
P&L:       +125.50
```

🤖 **AI Decisions** — Every ATLAS/LLM decision (HOLD suppressed by default)
```
🤖 Decision Digest
Symbol:     ETH-USD
Action:     BUY
Confidence: 0.85
Rationale:  [Groq (llama-3.3-70b)] [TRENDING] 3/3 layers agree: MACD bullish crossover...
```

📊 **Session Summary** — When trading stops
```
📊 Session Summary
Total P&L:    +1,234.56
Win Rate:     65.0%
Total Trades: 20
Sharpe:       1.4523
Max Drawdown: 3.2500%
```

---

## Security Notes

⚠️ **Keep your bot token secret!**
- Never commit `keys.env` to git (it's already in `.gitignore`)
- Your bot token gives full control over your bot
- Your chat ID is less sensitive but still keep it private

⚠️ **Bot token format:**
- Must be: `NNNNNNNNN:XXXXXXXXXXXXXXXXXXXXXXXXXXX`
- Numbers before `:`, letters/numbers after
- No spaces, quotes, or extra characters

---

## Troubleshooting

### "WARNING: Telegram disabled — FileNotFoundError"
- **Fix:** Create `keys.env` in project root with credentials

### "WARNING: Telegram disabled — ValueError"
- **Fix:** Check that both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set

### Bot doesn't respond to commands
- **Fix:** 
  1. Verify `run_hour.py --telegram` is running
  2. Check console for "Telegram bot started (polling enabled)"
  3. Restart the bot and send `/start` to your bot first

### Bot sends duplicate messages
- **Fix:** Only run one instance of `run_hour.py --telegram` at a time

---

## Running Without Telegram

If you don't want Telegram notifications, simply omit the `--telegram` flag:

```bash
# No Telegram notifications
py -3 run_hour.py --strategy ATLAS --minutes 60
```

The system works perfectly fine without Telegram — it's optional!

---

## Next: Alpaca Setup

If you also want to use `--alpaca` for live broker integration, see `ALPACA_SETUP.md`.
