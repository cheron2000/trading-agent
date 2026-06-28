"""
================================================================================
  ADAPTIVE AI TRADING AGENT — GOOGLE COLAB MASTER NOTEBOOK
  Phases 1 → 4 | Real-Time Data - LLM Decisions - Paper Trading
================================================================================
  INSTRUCTIONS (run each cell block in order inside Google Colab):
  1. Paste each CELL into a separate Colab code cell.
  2. Set your Anthropic API key in CELL 2 when prompted.
  3. Run cells sequentially. Cell 6 is the live trading loop.
================================================================================
"""


# ============================================================
# CELL 1 — Install Dependencies
# ============================================================
"""
Paste this into Colab Cell 1 and run it first.
"""

CELL_1 = """
!pip install -q yfinance groq pandas numpy

import importlib, sys
for pkg in ["yfinance", "groq", "pandas", "numpy"]:
    if importlib.util.find_spec(pkg) is None:
        raise ImportError(f"Package '{pkg}' failed to install. Check your runtime.")

print("[DONE] All dependencies installed successfully.")
"""


# ============================================================
# CELL 2 — Configuration & API Key Setup
# ============================================================
"""
Paste this into Colab Cell 2.
"""

CELL_2 = """
import os
from getpass import getpass

# -- API KEY --------------------------------------------------
GROQ_API_KEY = getpass("🔑 Enter your Groq API Key (starts with gsk_): ")
os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# -- AGENT CONFIGURATION --------------------------------------
CONFIG = {
    # Assets to trade (Yahoo Finance tickers)
    "watchlist": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "AVAX-USD"],

    # Paper trading starting capital (USD)
    "starting_capital": 100_000.0,

    # Max % of portfolio to risk per trade
    "max_position_pct": 0.10,           # 10% per trade

    # Minimum AI confidence score to act on (0.0 → 1.0)
    "confidence_threshold": 0.65,

    # Polling interval between live analysis cycles (seconds)
    # Crypto trades 24/7 — shorter intervals are fine
    "poll_interval_seconds": 60,

    # Number of trading cycles to run (set to None for infinite)
    "max_cycles": 5,

    # LLM model to use
    "model": "llama-3.3-70b-versatile",   # Free via Groq

    # Lookback window for price history (days)
    "price_history_days": 30,

    # Crypto-specific settings
    "asset_class": "CRYPTO",            # switches sentiment source + labels
    "crypto_interval": "1h",           # 1h candles for intraday signals
    "min_trade_notional": 10.0,        # min $10 per trade (crypto is divisible)
}

print("[DONE] Configuration loaded.")
print(f"   Watchlist  : {CONFIG['watchlist']}")
print(f"   Capital    : ${CONFIG['starting_capital']:,.2f}")
print(f"   Max Risk   : {CONFIG['max_position_pct']*100:.0f}% per trade")
print(f"   Confidence : >{CONFIG['confidence_threshold']}")
print(f"   Cycles     : {CONFIG['max_cycles']}")
"""


# ============================================================
# CELL 3 — Phase 1 & 2: Live Market Data Pipeline
# ============================================================
"""
Paste this into Colab Cell 3.
This is the multi-factor ingestion pipeline that builds the Market State Vector.
"""

CELL_3 = """
import yfinance as yf
import urllib.request
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import json
import time
import re
from datetime import datetime, timezone


# -- TECHNICAL INDICATOR HELPERS -------------------------------

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    \"\"\"Relative Strength Index — momentum oscillator (0–100).\"\"\"
    delta = series.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2) if not rsi.empty else 50.0


def compute_macd(series: pd.Series):
    \"\"\"MACD line, signal line, and histogram.\"\"\"
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return (
        round(float(macd.iloc[-1]), 4),
        round(float(signal.iloc[-1]), 4),
        round(float(hist.iloc[-1]), 4),
    )


def compute_bollinger(series: pd.Series, period: int = 20):
    \"\"\"Bollinger Bands — upper, middle (SMA), lower.\"\"\"
    sma   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = sma + (2 * std)
    lower = sma - (2 * std)
    return (
        round(float(upper.iloc[-1]), 2),
        round(float(sma.iloc[-1]), 2),
        round(float(lower.iloc[-1]), 2),
    )


def compute_atr(high, low, close, period: int = 14) -> float:
    \"\"\"Average True Range — volatility measure.\"\"\"
    h_l   = high - low
    h_pc  = abs(high - close.shift(1))
    l_pc  = abs(low  - close.shift(1))
    tr    = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    atr   = tr.rolling(period).mean()
    return round(float(atr.iloc[-1]), 4) if not atr.empty else 0.0


def compute_vwap(df: pd.DataFrame) -> float:
    \"\"\"Volume Weighted Average Price (rolling session).\"\"\"
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    vwap    = (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return round(float(vwap.iloc[-1]), 2)


# -- SENTIMENT PIPELINE -----------------------------------------

def fetch_sentiment(ticker: str, max_headlines: int = 5) -> dict:
    \"\"\"
    Pulls latest Yahoo Finance RSS headlines for a ticker.
    Returns a dict with raw headlines and a naive sentiment score.
    \"\"\"
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    headlines = []
    sentiment_score = 0.0

    # Simple keyword polarity wordlists
    positive_words = {
        "surge", "soar", "beat", "record", "bullish", "upgrade",
        "growth", "profit", "gain", "rally", "strong", "buy",
        "boost", "positive", "rise", "high", "exceed", "win",
    }
    negative_words = {
        "plunge", "crash", "miss", "bearish", "downgrade", "loss",
        "decline", "fall", "weak", "sell", "cut", "negative",
        "drop", "low", "risk", "warn", "concern", "fear",
    }

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")[:max_headlines]

        for item in items:
            title = item.findtext("title", default="").strip()
            if not title:
                continue
            headlines.append(title)
            words = set(re.sub(r"[^a-z ]", "", title.lower()).split())
            pos = len(words & positive_words)
            neg = len(words & negative_words)
            sentiment_score += (pos - neg)

        # Normalise to [-1, +1]
        if headlines:
            sentiment_score = max(-1.0, min(1.0, sentiment_score / (len(headlines) * 3)))

    except Exception as e:
        headlines = [f"[Sentiment feed unavailable: {e}]"]
        sentiment_score = 0.0

    label = "POSITIVE" if sentiment_score > 0.1 else ("NEGATIVE" if sentiment_score < -0.1 else "NEUTRAL")
    return {
        "headlines": headlines,
        "sentiment_score": round(sentiment_score, 3),
        "sentiment_label": label,
    }


# -- MARKET STATE VECTOR BUILDER -------------------------------

# -- CRYPTO SENTIMENT (CoinGecko RSS + crypto keyword lists) --

CRYPTO_TICKER_MAP = {
    "BTC-USD"  : ("bitcoin",  "BTC"),
    "ETH-USD"  : ("ethereum", "ETH"),
    "SOL-USD"  : ("solana",   "SOL"),
    "BNB-USD"  : ("bnb",      "BNB"),
    "AVAX-USD" : ("avalanche","AVAX"),
    "DOGE-USD" : ("dogecoin", "DOGE"),
    "XRP-USD"  : ("ripple",   "XRP"),
    "ADA-USD"  : ("cardano",  "ADA"),
}

def fetch_crypto_sentiment(ticker: str, max_headlines: int = 5) -> dict:
    """
    Pulls crypto news from CoinTelegraph RSS + Yahoo Finance RSS.
    Uses crypto-specific bullish/bearish keyword lists.
    """
    coin_id, coin_symbol = CRYPTO_TICKER_MAP.get(ticker, ("bitcoin", "BTC"))

    positive_words = {
        "surge", "soar", "rally", "bullish", "breakout", "adoption",
        "upgrade", "partnership", "record", "high", "gain", "moon",
        "accumulate", "buy", "institutional", "etf", "approval",
        "milestone", "growth", "halving", "listing", "integration",
    }
    negative_words = {
        "crash", "plunge", "bearish", "hack", "exploit", "ban",
        "regulation", "lawsuit", "sell", "dump", "fear", "panic",
        "liquidation", "scam", "fraud", "warning", "decline", "drop",
        "loss", "risk", "concern", "investigation", "delist",
    }

    headlines      = []
    sentiment_score = 0.0

    # Try multiple RSS sources for crypto
    rss_urls = [
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        f"https://cointelegraph.com/rss/tag/{coin_id}",
    ]

    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                xml_data = resp.read()
            root  = ET.fromstring(xml_data)
            items = root.findall(".//item")[:max_headlines]
            for item in items:
                title = item.findtext("title", default="").strip()
                if not title or title in headlines:
                    continue
                headlines.append(title)
                words = set(re.sub(r"[^a-z ]", "", title.lower()).split())
                pos = len(words & positive_words)
                neg = len(words & negative_words)
                sentiment_score += (pos - neg)
            if headlines:
                break   # got enough from first working source
        except Exception:
            continue

    if not headlines:
        headlines       = ["[Crypto sentiment feed unavailable]"]
        sentiment_score = 0.0

    if headlines and headlines[0] != "[Crypto sentiment feed unavailable]":
        sentiment_score = max(-1.0, min(1.0, sentiment_score / (len(headlines) * 3)))

    label = "POSITIVE" if sentiment_score > 0.1 else ("NEGATIVE" if sentiment_score < -0.1 else "NEUTRAL")
    return {
        "headlines"       : headlines,
        "sentiment_score" : round(sentiment_score, 3),
        "sentiment_label" : label,
        "source"          : "CryptoRSS",
    }


def build_market_state_vector(ticker: str, history_days: int = 30) -> str:
    \"\"\"
    Aggregates real-time price data + sentiment into a single
    structured string (the Market State Vector) ready for LLM ingestion.
    \"\"\"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        stock    = yf.Ticker(ticker)
        is_crypto = CONFIG.get("asset_class") == "CRYPTO"
        interval  = CONFIG.get("crypto_interval", "1h") if is_crypto else "1d"
        # For hourly crypto: fetch last 30 days at 1h resolution
        period    = f"{min(history_days, 29)}d" if is_crypto else f"{history_days}d"
        df        = stock.history(period=period, interval=interval)
        info  = stock.fast_info

        if df.empty or len(df) < 20:
            return f"[ERROR] Insufficient price data for {ticker}."

        close  = df["Close"]
        volume = df["Volume"]
        high   = df["High"]
        low    = df["Low"]

        # -- Price levels
        current_price  = round(float(close.iloc[-1]), 2)
        prev_close     = round(float(close.iloc[-2]), 2)
        day_change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)
        week_change    = round(((current_price - float(close.iloc[-6])) / float(close.iloc[-6])) * 100, 2)
        month_change   = round(((current_price - float(close.iloc[0]))  / float(close.iloc[0]))  * 100, 2)

        # -- Technical indicators
        rsi                    = compute_rsi(close)
        macd, macd_sig, macd_h = compute_macd(close)
        bb_up, bb_mid, bb_low  = compute_bollinger(close)
        atr                    = compute_atr(high, low, close)
        vwap                   = compute_vwap(df)
        sma_20                 = round(float(close.rolling(20).mean().iloc[-1]), 2)
        sma_50_series          = close.rolling(50).mean()
        sma_50                 = round(float(sma_50_series.iloc[-1]), 2) if not sma_50_series.dropna().empty else None
        ema_9                  = round(float(close.ewm(span=9).mean().iloc[-1]), 2)

        # -- Volume analysis
        avg_vol_10d   = round(float(volume.rolling(10).mean().iloc[-1]))
        current_vol   = round(float(volume.iloc[-1]))
        vol_ratio     = round(current_vol / avg_vol_10d, 2) if avg_vol_10d > 0 else 1.0

        # -- Market cap tier
        try:
            mkt_cap = info.market_cap
            if   mkt_cap >= 200e9: cap_tier = "Mega-cap (>$200B)"
            elif mkt_cap >= 10e9:  cap_tier = "Large-cap ($10B–$200B)"
            elif mkt_cap >= 2e9:   cap_tier = "Mid-cap ($2B–$10B)"
            else:                  cap_tier = "Small-cap (<$2B)"
        except Exception:
            cap_tier = "Unknown"

        # -- Momentum signals
        price_vs_sma20  = "ABOVE" if current_price > sma_20 else "BELOW"
        price_vs_vwap   = "ABOVE" if current_price > vwap   else "BELOW"
        bb_position     = (
            "UPPER_BAND"  if current_price >= bb_up  else
            "LOWER_BAND"  if current_price <= bb_low else
            "MIDDLE_BAND"
        )
        macd_crossover  = "BULLISH_CROSS" if macd_h > 0 else "BEARISH_CROSS"
        rsi_zone        = (
            "OVERBOUGHT"  if rsi > 70 else
            "OVERSOLD"    if rsi < 30 else
            "NEUTRAL"
        )

        # -- Sentiment (crypto-aware)
        sentiment = fetch_crypto_sentiment(ticker) if CONFIG.get("asset_class") == "CRYPTO" else fetch_sentiment(ticker)

        # -- Crypto asset label
        asset_type = "CRYPTOCURRENCY" if CONFIG.get("asset_class") == "CRYPTO" else "EQUITY"
        asset_label = CRYPTO_TICKER_MAP.get(ticker, (ticker, ticker))[1] if CONFIG.get("asset_class") == "CRYPTO" else ticker

        # -- Assemble the Market State Vector
        vector = f\"\"\"
=== LIVE MARKET STATE VECTOR ===
Timestamp  : {now}
Asset      : {ticker}
Market Cap : {cap_tier}

--- PRICE ACTION ---
Current Price  : ${current_price}
Prev Close     : ${prev_close}
Day Change     : {day_change_pct:+.2f}%
Week Change    : {week_change:+.2f}%
Month Change   : {month_change:+.2f}%

--- TECHNICAL INDICATORS ---
RSI(14)        : {rsi}  [{rsi_zone}]
MACD           : {macd}  |  Signal: {macd_sig}  |  Histogram: {macd_h}  [{macd_crossover}]
Bollinger Bands: Upper={bb_up}  Mid={bb_mid}  Lower={bb_low}  [Price at: {bb_position}]
ATR(14)        : {atr}  (volatility proxy)
VWAP           : ${vwap}  [Price is {price_vs_vwap} VWAP]
SMA(20)        : ${sma_20}  [Price is {price_vs_sma20} SMA20]
SMA(50)        : {"$"+str(sma_50) if sma_50 else "Insufficient data"}
EMA(9)         : ${ema_9}

--- VOLUME ANALYSIS ---
Current Volume : {current_vol:,}
Avg Vol (10d)  : {avg_vol_10d:,}
Volume Ratio   : {vol_ratio}x  {"[HIGH VOLUME — conviction signal]" if vol_ratio > 1.5 else "[Normal volume]"}

--- SENTIMENT ANALYSIS ---
Sentiment      : {sentiment['sentiment_label']}  (score: {sentiment['sentiment_score']})
Recent Headlines:
{chr(10).join(f"  - {h}" for h in sentiment['headlines'])}
=================================
\"\"\"
        return vector.strip()

    except Exception as e:
        return f"[ERROR] Failed to build market state vector for {ticker}: {e}"


print("[DONE] Phase 1 & 2 — Market Data Pipeline loaded.")
print("   Test with: print(build_market_state_vector('AAPL'))")
"""


# ============================================================
# CELL 4 — Phase 3: LLM Decision Engine
# ============================================================
"""
Paste this into Colab Cell 4.
"""

CELL_4 = """
from groq import Groq
import json
import re

client = Groq(api_key=os.environ["GROQ_API_KEY"])


SYSTEM_PROMPT = \"\"\"
You are ATLAS — an Adaptive Tactical LLM Algorithmic System — an elite quantitative
crypto trading analyst embedded within a live paper-trading execution desk.

You specialise in cryptocurrency markets (BTC, ETH, SOL, BNB, AVAX and others).
Crypto markets trade 24/7, are highly volatile, and are heavily influenced by
on-chain sentiment, macro risk appetite, and momentum. Factor these in.

Your sole function is to ingest a real-time Market State Vector and produce a
precise, machine-executable tactical trading decision in strict JSON format.

=== DECISION FRAMEWORK ===
Synthesise ALL available signals holistically:
  - Momentum  : RSI zone, MACD crossover, EMA/SMA positioning
  - Volatility: ATR level, Bollinger Band position (crypto = wider bands normal)
  - Volume    : Ratio vs 10-day average (conviction gauge)
  - Sentiment : Crypto news polarity — regulatory, institutional, on-chain events
  - Price     : Hour/Day/Week trend direction
  - Crypto    : 24/7 market — weekend gaps don't exist; liquidity varies by hour

=== OUTPUT RULES — CRITICAL ===
1. Respond with ONLY valid JSON. No preamble. No explanation. No markdown fences.
2. The JSON must match this exact schema — no extra or missing keys:
{
  "asset": "<TICKER>",
  "tactical_stance": "<BUY | SELL | HOLD>",
  "confidence_score": <float 0.0–1.0>,
  "rationale": "<max 3 concise sentences explaining the dominant signals>",
  "execution_parameters": {
    "entry_trigger": "<exact condition to enter, e.g. price > $X>",
    "target_take_profit": "<price level or % gain>",
    "stop_loss_limit": "<price level or % loss>"
  },
  "signal_breakdown": {
    "momentum_signal": "<BULLISH | BEARISH | NEUTRAL>",
    "volatility_signal": "<HIGH | MODERATE | LOW>",
    "volume_signal": "<CONFIRMING | WEAK | DIVERGING>",
    "sentiment_signal": "<POSITIVE | NEGATIVE | NEUTRAL>"
  }
}
3. confidence_score must reflect genuine signal convergence:
   - 0.85–1.0 : Strong multi-factor confluence
   - 0.65–0.84: Moderate conviction, clear primary signal
   - 0.40–0.64: Mixed signals, lean toward HOLD
   - 0.00–0.39: High uncertainty, HOLD mandatory
4. NEVER fabricate data. Base decisions solely on the vector provided.
5. If signals are genuinely conflicting, output HOLD with low confidence.
\"\"\"


def get_ai_decision(market_state_vector: str, ticker: str) -> dict:
    \"\"\"
    Sends the Market State Vector to Claude and returns a parsed
    tactical decision dictionary.
    \"\"\"
    user_message = f\"\"\"
Analyse the following live Market State Vector and output your tactical decision
in strict JSON format per your system instructions.

{market_state_vector}

Asset under analysis: {ticker}
Respond with JSON only.
\"\"\"

    try:
        response = client.chat.completions.create(
            model=CONFIG["model"],
            max_tokens=800,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )

        raw_text = response.choices[0].message.content.strip()

        # Strip any accidental markdown fences
        raw_text = re.sub(r"^```[a-z]*\\n?", "", raw_text)
        raw_text = re.sub(r"\\n?```$", "", raw_text)

        decision = json.loads(raw_text)

        # Validate required keys
        required_keys = {
            "asset", "tactical_stance", "confidence_score",
            "rationale", "execution_parameters", "signal_breakdown"
        }
        missing = required_keys - set(decision.keys())
        if missing:
            raise ValueError(f"Missing keys in LLM response: {missing}")

        decision["tactical_stance"] = decision["tactical_stance"].upper().strip()
        if decision["tactical_stance"] not in ("BUY", "SELL", "HOLD"):
            decision["tactical_stance"] = "HOLD"

        return {"status": "ok", "decision": decision, "raw": raw_text}

    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"JSON parse failed: {e}", "raw": raw_text}
    except Exception as e:
        return {"status": "error", "error": str(e), "raw": ""}


print("[DONE] Phase 3 — LLM Decision Engine (ATLAS) loaded.")
"""


# ============================================================
# CELL 5 — Phase 4: Portfolio & Paper Trade Execution Engine
# ============================================================
"""
Paste this into Colab Cell 5.
"""

CELL_5 = """
from dataclasses import dataclass, field
from typing import Optional
import uuid


# -- DATA STRUCTURES -------------------------------------------

@dataclass
class Position:
    \"\"\"Represents a single open paper trade position.\"\"\"
    position_id    : str
    ticker         : str
    stance         : str          # BUY or SELL (short)
    entry_price    : float
    shares         : float
    notional_value : float        # USD allocated
    stop_loss      : float
    take_profit    : float
    confidence     : float
    opened_at      : str
    rationale      : str


@dataclass
class ClosedTrade:
    \"\"\"Record of a completed trade for performance tracking.\"\"\"
    position_id  : str
    ticker       : str
    stance       : str
    entry_price  : float
    exit_price   : float
    shares       : float
    pnl_usd      : float
    pnl_pct      : float
    outcome      : str            # WIN / LOSS / BREAK_EVEN
    opened_at    : str
    closed_at    : str
    close_reason : str            # TAKE_PROFIT / STOP_LOSS / SIGNAL_REVERSAL / CYCLE_END


class PaperPortfolio:
    \"\"\"
    Manages the simulated paper trading portfolio.
    Tracks cash, open positions, closed trades, and performance metrics.
    \"\"\"

    def __init__(self, starting_capital: float, max_position_pct: float):
        self.starting_capital   = starting_capital
        self.cash               = starting_capital
        self.max_position_pct   = max_position_pct
        self.open_positions     : dict[str, Position] = {}   # ticker → Position
        self.closed_trades      : list[ClosedTrade]   = []
        self.trade_log          : list[dict]          = []   # full event log
        self.cycle_count        = 0
        self.created_at         = datetime.now(timezone.utc).isoformat()

    # -- PORTFOLIO VALUE ----------------------------------------

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        \"\"\"Cash + mark-to-market value of all open positions.\"\"\"
        position_value = 0.0
        for ticker, pos in self.open_positions.items():
            price = current_prices.get(ticker, pos.entry_price)
            if pos.stance == "BUY":
                position_value += pos.shares * price
            else:  # SHORT
                # Profit from short = (entry - current) * shares + entry notional
                pnl = (pos.entry_price - price) * pos.shares
                position_value += pos.notional_value + pnl
        return self.cash + position_value

    # -- OPEN A POSITION ----------------------------------------

    def open_position(
        self,
        ticker        : str,
        stance        : str,
        current_price : float,
        stop_loss_pct : float,
        take_profit_pct: float,
        confidence    : float,
        rationale     : str,
    ) -> Optional[Position]:
        \"\"\"
        Opens a new position if:
        - No existing open position on this ticker.
        - Sufficient cash available.
        - Stance is BUY or SELL (not HOLD).
        \"\"\"
        if stance == "HOLD":
            return None

        if ticker in self.open_positions:
            self._log(f"[SKIP] Already have open position in {ticker}.")
            return None

        # Position size = max_position_pct of current total portfolio
        est_portfolio = self.cash  # rough estimate before mark-to-market
        notional = est_portfolio * self.max_position_pct

        if notional > self.cash:
            self._log(f"[SKIP] Insufficient cash to open {ticker} position.")
            return None

        shares = notional / current_price

        # Set stop/take-profit levels
        if stance == "BUY":
            stop_loss   = round(current_price * (1 - stop_loss_pct / 100), 2)
            take_profit = round(current_price * (1 + take_profit_pct / 100), 2)
        else:  # SHORT
            stop_loss   = round(current_price * (1 + stop_loss_pct / 100), 2)
            take_profit = round(current_price * (1 - take_profit_pct / 100), 2)

        pos = Position(
            position_id    = str(uuid.uuid4())[:8],
            ticker         = ticker,
            stance         = stance,
            entry_price    = current_price,
            shares         = round(shares, 4),
            notional_value = round(notional, 2),
            stop_loss      = stop_loss,
            take_profit    = take_profit,
            confidence     = confidence,
            opened_at      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            rationale      = rationale,
        )

        self.cash -= notional
        self.open_positions[ticker] = pos

        self._log(
            f"[OPEN] {stance} {ticker} | {shares:.2f} shares @ ${current_price:.2f} "
            f"| Notional: ${notional:,.2f} | SL: ${stop_loss} | TP: ${take_profit} "
            f"| Confidence: {confidence:.2f}"
        )
        return pos

    # -- CLOSE A POSITION ----------------------------------------

    def close_position(
        self,
        ticker       : str,
        exit_price   : float,
        close_reason : str,
    ) -> Optional[ClosedTrade]:
        \"\"\"Closes an open position and records the trade outcome.\"\"\"
        if ticker not in self.open_positions:
            return None

        pos = self.open_positions.pop(ticker)

        if pos.stance == "BUY":
            pnl_usd = (exit_price - pos.entry_price) * pos.shares
            returned_cash = pos.shares * exit_price
        else:  # SHORT
            pnl_usd = (pos.entry_price - exit_price) * pos.shares
            returned_cash = pos.notional_value + pnl_usd

        pnl_pct  = round((pnl_usd / pos.notional_value) * 100, 2)
        pnl_usd  = round(pnl_usd, 2)
        outcome  = "WIN" if pnl_usd > 0 else ("LOSS" if pnl_usd < 0 else "BREAK_EVEN")

        self.cash += returned_cash

        trade = ClosedTrade(
            position_id  = pos.position_id,
            ticker       = ticker,
            stance       = pos.stance,
            entry_price  = pos.entry_price,
            exit_price   = round(exit_price, 2),
            shares       = pos.shares,
            pnl_usd      = pnl_usd,
            pnl_pct      = pnl_pct,
            outcome      = outcome,
            opened_at    = pos.opened_at,
            closed_at    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            close_reason = close_reason,
        )
        self.closed_trades.append(trade)

        emoji = "[DONE]" if outcome == "WIN" else ("[FAIL]" if outcome == "LOSS" else "[FLAT]")
        self._log(
            f"[CLOSE] {emoji} {ticker} @ ${exit_price:.2f} | PnL: ${pnl_usd:+,.2f} "
            f"({pnl_pct:+.2f}%) | Reason: {close_reason}"
        )
        return trade

    # -- STOP/TAKE-PROFIT CHECKER -----------------------------

    def check_exit_conditions(self, current_prices: dict[str, float]) -> list[ClosedTrade]:
        \"\"\"Auto-closes positions that hit stop-loss or take-profit.\"\"\"
        exits = []
        for ticker, pos in list(self.open_positions.items()):
            price = current_prices.get(ticker)
            if price is None:
                continue

            if pos.stance == "BUY":
                if price <= pos.stop_loss:
                    exits.append(self.close_position(ticker, price, "STOP_LOSS"))
                elif price >= pos.take_profit:
                    exits.append(self.close_position(ticker, price, "TAKE_PROFIT"))
            else:  # SHORT
                if price >= pos.stop_loss:
                    exits.append(self.close_position(ticker, price, "STOP_LOSS"))
                elif price <= pos.take_profit:
                    exits.append(self.close_position(ticker, price, "TAKE_PROFIT"))
        return [t for t in exits if t is not None]

    # -- PERFORMANCE METRICS ------------------------------------

    def get_performance_metrics(self, current_prices: dict[str, float]) -> dict:
        \"\"\"Returns a comprehensive snapshot of portfolio performance.\"\"\"
        total_value    = self.get_portfolio_value(current_prices)
        total_pnl      = total_value - self.starting_capital
        total_return   = (total_pnl / self.starting_capital) * 100

        wins   = [t for t in self.closed_trades if t.outcome == "WIN"]
        losses = [t for t in self.closed_trades if t.outcome == "LOSS"]
        n      = len(self.closed_trades)

        win_rate      = (len(wins) / n * 100) if n > 0 else 0.0
        avg_win       = (sum(t.pnl_usd for t in wins)   / len(wins))   if wins   else 0.0
        avg_loss      = (sum(t.pnl_usd for t in losses) / len(losses)) if losses else 0.0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # Max drawdown
        if self.closed_trades:
            cumulative = self.starting_capital
            peak       = self.starting_capital
            max_dd     = 0.0
            for t in self.closed_trades:
                cumulative += t.pnl_usd
                peak        = max(peak, cumulative)
                drawdown    = (peak - cumulative) / peak * 100
                max_dd      = max(max_dd, drawdown)
        else:
            max_dd = 0.0

        return {
            "portfolio_value"   : round(total_value, 2),
            "starting_capital"  : self.starting_capital,
            "cash_available"    : round(self.cash, 2),
            "open_positions"    : len(self.open_positions),
            "total_pnl_usd"     : round(total_pnl, 2),
            "total_return_pct"  : round(total_return, 2),
            "total_trades"      : n,
            "wins"              : len(wins),
            "losses"            : len(losses),
            "win_rate_pct"      : round(win_rate, 1),
            "avg_win_usd"       : round(avg_win, 2),
            "avg_loss_usd"      : round(avg_loss, 2),
            "profit_factor"     : round(profit_factor, 2),
            "max_drawdown_pct"  : round(max_dd, 2),
            "cycles_completed"  : self.cycle_count,
        }

    # -- DISPLAY HELPERS ----------------------------------------

    def print_dashboard(self, current_prices: dict[str, float]):
        \"\"\"Prints a formatted portfolio dashboard to the console.\"\"\"
        m  = self.get_performance_metrics(current_prices)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        print("\\n" + "="*62)
        print(f"  [DASHBOARD]  ATLAS PAPER TRADING DASHBOARD  -  {ts}")
        print("="*62)
        print(f"  Portfolio Value   : ${m['portfolio_value']:>12,.2f}")
        print(f"  Cash Available    : ${m['cash_available']:>12,.2f}")
        print(f"  Open Positions    : {m['open_positions']:>12}")
        print(f"  Total PnL         : ${m['total_pnl_usd']:>+12,.2f}  ({m['total_return_pct']:+.2f}%)")
        print("-"*62)
        print(f"  Completed Trades  : {m['total_trades']:>12}")
        print(f"  Win Rate          : {m['win_rate_pct']:>11.1f}%")
        print(f"  Avg Win           : ${m['avg_win_usd']:>+12,.2f}")
        print(f"  Avg Loss          : ${m['avg_loss_usd']:>+12,.2f}")
        print(f"  Profit Factor     : {m['profit_factor']:>12.2f}")
        print(f"  Max Drawdown      : {m['max_drawdown_pct']:>11.2f}%")
        print(f"  Cycles Completed  : {m['cycles_completed']:>12}")
        print("-"*62)

        if self.open_positions:
            print("  OPEN POSITIONS:")
            for ticker, pos in self.open_positions.items():
                cur = current_prices.get(ticker, pos.entry_price)
                if pos.stance == "BUY":
                    unrealised = (cur - pos.entry_price) * pos.shares
                else:
                    unrealised = (pos.entry_price - cur) * pos.shares
                flag = "[LONG]" if unrealised >= 0 else "[SHORT]"
                print(
                    f"    {flag} [{pos.stance}] {ticker} | Entry: ${pos.entry_price:.2f} "
                    f"| Now: ${cur:.2f} | Unreal PnL: ${unrealised:+,.2f} "
                    f"| SL: ${pos.stop_loss} | TP: ${pos.take_profit}"
                )
        else:
            print("  No open positions.")

        print("="*62 + "\\n")

    def _log(self, msg: str):
        ts  = datetime.now(timezone.utc).strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.trade_log.append(entry)
        print(entry)


print("[DONE] Phase 4 — Paper Trading Portfolio Engine loaded.")
"""


# ============================================================
# CELL 6 — LIVE TRADING LOOP (Main Execution)
# ============================================================
"""
Paste this into Colab Cell 6.
This is the main execution loop — runs everything end to end.
"""

CELL_6 = """
import time

# -- STOP/TAKE-PROFIT DEFAULTS (% from entry) ------------------
# These are fallbacks; the AI's execution_parameters take precedence
# where they contain parseable numeric levels.
DEFAULT_STOP_LOSS_PCT    = 2.5    # 2.5% below entry
DEFAULT_TAKE_PROFIT_PCT  = 5.0    # 5.0% above entry


def parse_price_level(value_str: str, reference_price: float, is_pct_fallback: float) -> float:
    \"\"\"
    Extracts a numeric price level from the AI's execution_parameters string.
    Falls back to a percentage-based level if parsing fails.
    \"\"\"
    if not value_str:
        return reference_price * (1 + is_pct_fallback / 100)

    # Try to extract first dollar amount or raw number
    matches = re.findall(r"\\$?([\\d]+\\.?[\\d]*)", str(value_str))
    if matches:
        candidate = float(matches[0])
        # Sanity check: must be within 50% of the reference price
        if 0.5 * reference_price < candidate < 2.0 * reference_price:
            return candidate

    # Fallback to percentage
    return round(reference_price * (1 + is_pct_fallback / 100), 2)


def run_trading_loop():
    \"\"\"
    Main live paper trading loop.
    Each cycle:
      1. Fetches live market data for all watchlist assets.
      2. Checks stop-loss / take-profit on open positions.
      3. Sends Market State Vectors to ATLAS for decisions.
      4. Executes paper trades based on decisions.
      5. Prints a full portfolio dashboard.
    \"\"\"

    portfolio = PaperPortfolio(
        starting_capital  = CONFIG["starting_capital"],
        max_position_pct  = CONFIG["max_position_pct"],
    )

    watchlist         = CONFIG["watchlist"]
    max_cycles        = CONFIG["max_cycles"]
    poll_interval     = CONFIG["poll_interval_seconds"]
    conf_threshold    = CONFIG["confidence_threshold"]
    cycle             = 0
    performance_log   = []   # stores metrics snapshot each cycle

    print("\\n" + "="*62)
    print("  [START]  ATLAS ADAPTIVE AI TRADING AGENT — LIVE (PAPER)")
    print(f"  Capital: ${CONFIG['starting_capital']:,.2f}  |  Watchlist: {watchlist}")
    print("="*62 + "\\n")

    try:
        while True:
            cycle += 1
            portfolio.cycle_count = cycle
            cycle_start = datetime.now(timezone.utc)

            print(f"\\n{'-'*62}")
            print(f"  [CYCLE]  CYCLE {cycle}  |  {cycle_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"{'-'*62}")

            # -- STEP 1: Fetch current prices for all watchlist assets --
            current_prices = {}
            for ticker in watchlist:
                try:
                    px = yf.Ticker(ticker).fast_info.last_price
                    if px and px > 0:
                        current_prices[ticker] = round(float(px), 2)
                except Exception:
                    pass

            print(f"  [PRICES] Current prices: {current_prices}")

            # -- STEP 2: Check stop-loss / take-profit exits ------------
            exits = portfolio.check_exit_conditions(current_prices)
            if exits:
                print(f"  [AUTO-CLOSE] {len(exits)} position(s) auto-closed by SL/TP rules.")

            # -- STEP 3: Iterate watchlist — build vector → get decision -
            for ticker in watchlist:
                print(f"\\n  [SCAN] Analysing {ticker}...")

                # Build Market State Vector
                vector = build_market_state_vector(
                    ticker,
                    history_days=CONFIG["price_history_days"]
                )

                if vector.startswith("[ERROR]"):
                    print(f"  [WARNING]  {vector}")
                    continue

                # Get ATLAS decision
                result = get_ai_decision(vector, ticker)

                if result["status"] != "ok":
                    print(f"  [WARNING]  LLM error for {ticker}: {result.get('error')}")
                    continue

                decision   = result["decision"]
                stance     = decision["tactical_stance"]
                confidence = float(decision["confidence_score"])
                rationale  = decision["rationale"]
                exec_params = decision.get("execution_parameters", {})
                signals    = decision.get("signal_breakdown", {})

                print(f"  [ATLAS] ATLAS Decision: {stance} | Confidence: {confidence:.2f}")
                print(f"     Momentum: {signals.get('momentum_signal','?')} | "
                      f"Volatility: {signals.get('volatility_signal','?')} | "
                      f"Volume: {signals.get('volume_signal','?')} | "
                      f"Sentiment: {signals.get('sentiment_signal','?')}")
                print(f"     Rationale: {rationale}")

                cur_price = current_prices.get(ticker)
                if not cur_price:
                    print(f"  [WARNING]  No live price for {ticker} — skipping execution.")
                    continue

                # -- STEP 4a: SIGNAL REVERSAL — close opposite position --
                if ticker in portfolio.open_positions:
                    existing = portfolio.open_positions[ticker]
                    if (existing.stance == "BUY"  and stance == "SELL") or \
                       (existing.stance == "SELL" and stance == "BUY"):
                        print(f"  [REVERSAL] Signal reversal detected. Closing {existing.stance} position.")
                        portfolio.close_position(ticker, cur_price, "SIGNAL_REVERSAL")

                # -- STEP 4b: OPEN NEW POSITION -------------------------
                if stance in ("BUY", "SELL") and confidence >= conf_threshold:
                    if ticker not in portfolio.open_positions:
                        # Parse stop/take-profit from AI output
                        if stance == "BUY":
                            sl = parse_price_level(
                                exec_params.get("stop_loss_limit", ""),
                                cur_price,
                                -DEFAULT_STOP_LOSS_PCT,
                            )
                            tp = parse_price_level(
                                exec_params.get("target_take_profit", ""),
                                cur_price,
                                DEFAULT_TAKE_PROFIT_PCT,
                            )
                            sl_pct = abs((sl - cur_price) / cur_price * 100)
                            tp_pct = abs((tp - cur_price) / cur_price * 100)
                        else:  # SHORT
                            sl = parse_price_level(
                                exec_params.get("stop_loss_limit", ""),
                                cur_price,
                                DEFAULT_STOP_LOSS_PCT,
                            )
                            tp = parse_price_level(
                                exec_params.get("target_take_profit", ""),
                                cur_price,
                                -DEFAULT_TAKE_PROFIT_PCT,
                            )
                            sl_pct = abs((sl - cur_price) / cur_price * 100)
                            tp_pct = abs((tp - cur_price) / cur_price * 100)

                        portfolio.open_position(
                            ticker          = ticker,
                            stance          = stance,
                            current_price   = cur_price,
                            stop_loss_pct   = sl_pct,
                            take_profit_pct = tp_pct,
                            confidence      = confidence,
                            rationale       = rationale,
                        )
                else:
                    if stance == "HOLD":
                        print(f"  [SKIP]  HOLD signal — no action taken for {ticker}.")
                    elif confidence < conf_threshold:
                        print(
                            f"  [SKIP]  Confidence {confidence:.2f} below threshold "
                            f"{conf_threshold} — no trade on {ticker}."
                        )

            # -- STEP 5: Dashboard --------------------------------------
            portfolio.print_dashboard(current_prices)

            # Save performance snapshot
            snapshot = portfolio.get_performance_metrics(current_prices)
            snapshot["cycle"]     = cycle
            snapshot["timestamp"] = cycle_start.isoformat()
            performance_log.append(snapshot)

            # -- CHECK CYCLE LIMIT --------------------------------------
            if max_cycles and cycle >= max_cycles:
                print(f"\\n  [DONE] Reached max_cycles={max_cycles}. Ending session.")
                break

            # -- WAIT ---------------------------------------------------
            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            sleep_t = max(0, poll_interval - elapsed)
            print(f"  [WAIT] Next cycle in {sleep_t:.0f}s...")
            time.sleep(sleep_t)

    except KeyboardInterrupt:
        print("\\n  🛑 Trading session interrupted by user.")

    # -- FINAL SESSION REPORT -----------------------------------
    print("\\n" + "="*62)
    print("  [REPORT]  FINAL SESSION REPORT")
    print("="*62)

    final = portfolio.get_performance_metrics(current_prices)
    print(f"  Starting Capital  : ${final['starting_capital']:,.2f}")
    print(f"  Final Value       : ${final['portfolio_value']:,.2f}")
    print(f"  Total PnL         : ${final['total_pnl_usd']:+,.2f}  ({final['total_return_pct']:+.2f}%)")
    print(f"  Win Rate          : {final['win_rate_pct']:.1f}%  ({final['wins']}W / {final['losses']}L)")
    print(f"  Profit Factor     : {final['profit_factor']:.2f}")
    print(f"  Max Drawdown      : {final['max_drawdown_pct']:.2f}%")
    print(f"  Cycles Completed  : {final['cycles_completed']}")

    if portfolio.closed_trades:
        print("\\n  TRADE HISTORY:")
        for t in portfolio.closed_trades:
            icon = "[DONE]" if t.outcome == "WIN" else "[FAIL]"
            print(
                f"    {icon} [{t.stance}] {t.ticker} | "
                f"Entry: ${t.entry_price:.2f} → Exit: ${t.exit_price:.2f} | "
                f"PnL: ${t.pnl_usd:+,.2f} ({t.pnl_pct:+.2f}%) | {t.close_reason}"
            )

    print("\\n  FULL EVENT LOG:")
    for entry in portfolio.trade_log:
        print(f"    {entry}")

    print("="*62)
    return portfolio, performance_log


# -- RUN IT ----------------------------------------------------
portfolio, perf_log = run_trading_loop()
"""


# ============================================================
# CELL 7 — (Optional) Performance Chart
# ============================================================
"""
Paste this into Colab Cell 7 after the loop finishes.
Plots portfolio value over cycles using matplotlib (built into Colab).
"""

CELL_7 = """
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

if perf_log:
    cycles  = [s["cycle"]          for s in perf_log]
    values  = [s["portfolio_value"] for s in perf_log]
    pnl     = [s["total_pnl_usd"]  for s in perf_log]
    win_r   = [s["win_rate_pct"]   for s in perf_log]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    fig.patch.set_facecolor("#0d1117")
    for ax in axes:
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.title.set_color("white")
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")

    # Portfolio value
    axes[0].plot(cycles, values, color="#58a6ff", linewidth=2, marker="o")
    axes[0].axhline(CONFIG["starting_capital"], color="#8b949e", linestyle="--", linewidth=1)
    axes[0].set_title("Portfolio Value ($)", fontsize=12, pad=8)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    axes[0].set_xlabel("Cycle")

    # PnL bars
    colors = ["#3fb950" if p >= 0 else "#f85149" for p in pnl]
    axes[1].bar(cycles, pnl, color=colors)
    axes[1].axhline(0, color="#8b949e", linewidth=0.8)
    axes[1].set_title("Cumulative PnL ($)", fontsize=12, pad=8)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:+,.0f}"))
    axes[1].set_xlabel("Cycle")

    # Win rate
    axes[2].plot(cycles, win_r, color="#d2a8ff", linewidth=2, marker="s")
    axes[2].axhline(50, color="#8b949e", linestyle="--", linewidth=1)
    axes[2].set_title("Win Rate (%)", fontsize=12, pad=8)
    axes[2].set_ylim(0, 100)
    axes[2].set_xlabel("Cycle")

    fig.suptitle(
        "ATLAS — Paper Trading Session Performance",
        fontsize=14, color="white", y=1.01
    )
    plt.tight_layout()
    plt.savefig("atlas_performance.png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.show()
    print("\\n  [DASHBOARD] Chart saved as atlas_performance.png")
else:
    print("No performance data to chart yet. Run Cell 6 first.")
"""


# ============================================================
# PRINT SETUP GUIDE
# ============================================================

if __name__ == "__main__":
    print("""
╔==============================================================╗
║   ADAPTIVE AI TRADING AGENT — COLAB SETUP GUIDE             ║
╠==============================================================╣
║                                                              ║
║  Open Google Colab and create 7 cells.                       ║
║  Paste the content of each CELL_N variable above into        ║
║  the corresponding Colab code cell, then run in order.       ║
║                                                              ║
║  CELL 1 — Install dependencies                               ║
║  CELL 2 — Config & API key (enter your Anthropic key)        ║
║  CELL 3 — Market data pipeline (yfinance + sentiment)        ║
║  CELL 4 — ATLAS LLM decision engine                          ║
║  CELL 5 — Paper portfolio execution engine                   ║
║  CELL 6 — LIVE TRADING LOOP  ← main execution               ║
║  CELL 7 — Performance chart (optional, run after loop ends)  ║
║                                                              ║
║  To stop early: press the ■ STOP button in Colab, or use     ║
║  Runtime → Interrupt execution.                              ║
╚==============================================================╝
""")
