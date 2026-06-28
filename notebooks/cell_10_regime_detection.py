"""
================================================================================
  CELL 10 — Phase 3 Sub-Task 3.4: Market Regime Detection Layer
  Paste this into Colab Cell 10 and run it AFTER Cell 9, BEFORE Cell 6.
  Then apply the three targeted patches shown at the bottom to Cell 3 and Cell 6.
================================================================================

  REGIME CLASSIFICATION OVERVIEW
  ───────────────────────────────
  Each asset is independently classified into one of four regimes every cycle:

  ┌─────────────────┬──────────────────────────────────────────────────────┐
  │ Regime          │ Definition                                           │
  ├─────────────────┼──────────────────────────────────────────────────────┤
  │ TRENDING_BULL   │ Price above rising SMA20 & SMA50, ADX > 25,         │
  │                 │ MACD histogram positive, RSI 45–75                   │
  ├─────────────────┼──────────────────────────────────────────────────────┤
  │ TRENDING_BEAR   │ Price below falling SMA20 & SMA50, ADX > 25,        │
  │                 │ MACD histogram negative, RSI 25–55                   │
  ├─────────────────┼──────────────────────────────────────────────────────┤
  │ RANGING         │ ADX < 20, price oscillating inside Bollinger bands,  │
  │                 │ low directional bias, RSI near 50                    │
  ├─────────────────┼──────────────────────────────────────────────────────┤
  │ HIGH_VOLATILITY │ ATR > 2× its own 20-day average OR Bollinger Band    │
  │                 │ width > 8% of mid-band price                         │
  └─────────────────┴──────────────────────────────────────────────────────┘

  SCORING APPROACH
  ────────────────
  Rather than rigid if/else branches (which fail on edge cases), each regime
  accumulates evidence points from multiple independent signals. The regime
  with the highest score wins. Ties default to RANGING (most conservative).

  WHY ADX?
  ────────
  The Average Directional Index measures trend STRENGTH, not direction.
  ADX > 25 = trending market (bull or bear determined by +DI vs -DI).
  ADX < 20 = choppy/ranging market.
  It's computed purely from high/low/close — no new data sources needed.

  POSITION SIZE MODULATION
  ────────────────────────
  Regime multipliers are applied ON TOP of the Cell 8 Kelly sizing:

    TRENDING_BULL   → 1.00× (full size — high-quality environment)
    TRENDING_BEAR   → 0.50× (half size — counter-trend risk suppressed)
    RANGING         → 0.60× (reduced — mean-reversion not our edge)
    HIGH_VOLATILITY → 0.40× (severely reduced — wide stops eat capital)

  STANCE SUPPRESSION
  ──────────────────
  Hard rules applied before execution regardless of AI confidence:

    TRENDING_BEAR   → BUY signals suppressed → forced to HOLD
    TRENDING_BULL   → SELL (short) signals suppressed → forced to HOLD
    HIGH_VOLATILITY → confidence threshold raised by +0.10
    RANGING         → confidence threshold raised by +0.05
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone
from typing import Optional


# ─────────────────────────────────────────────────────────────
# REGIME CONSTANTS
# ─────────────────────────────────────────────────────────────

REGIME_TRENDING_BULL   = "TRENDING_BULL"
REGIME_TRENDING_BEAR   = "TRENDING_BEAR"
REGIME_RANGING         = "RANGING"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"

# Position size multipliers per regime (applied on top of Kelly)
REGIME_SIZE_MULTIPLIERS = {
    REGIME_TRENDING_BULL   : 1.00,
    REGIME_TRENDING_BEAR   : 0.50,
    REGIME_RANGING         : 0.60,
    REGIME_HIGH_VOLATILITY : 0.40,
}

# Confidence threshold additions per regime
REGIME_CONF_PENALTY = {
    REGIME_TRENDING_BULL   : 0.00,
    REGIME_TRENDING_BEAR   : 0.00,
    REGIME_RANGING         : 0.05,
    REGIME_HIGH_VOLATILITY : 0.10,
}

# Stance suppression rules: {regime: stance_to_suppress}
REGIME_SUPPRESSION = {
    REGIME_TRENDING_BEAR : "BUY",   # Don't buy into a downtrend
    REGIME_TRENDING_BULL : "SELL",  # Don't short a strong uptrend
}


# ─────────────────────────────────────────────────────────────
# TECHNICAL HELPERS (regime-specific)
# ─────────────────────────────────────────────────────────────

def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> tuple[float, float, float]:
    """
    Average Directional Index + Directional Indicators.
    Returns (ADX, +DI, -DI).

    ADX > 25 → trending; +DI > -DI → bullish trend; -DI > +DI → bearish.
    """
    high, low, close = high.copy(), low.copy(), close.copy()

    # True Range
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm  = np.where((up_move > down_move) & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=high.index).rolling(period).mean()
    minus_dm_s = pd.Series(minus_dm, index=high.index).rolling(period).mean()
    atr_s      = tr.rolling(period).mean()

    plus_di  = 100 * plus_dm_s  / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm_s / atr_s.replace(0, np.nan)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()

    def _last(s):
        v = s.dropna()
        return round(float(v.iloc[-1]), 2) if not v.empty else 0.0

    return _last(adx), _last(plus_di), _last(minus_di)


def compute_bb_width(close: pd.Series, period: int = 20) -> float:
    """
    Bollinger Band Width = (Upper - Lower) / Middle × 100.
    High values → expanding volatility; low values → squeeze.
    """
    sma   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    width = ((upper - lower) / sma.replace(0, np.nan)) * 100
    v     = width.dropna()
    return round(float(v.iloc[-1]), 2) if not v.empty else 0.0


def compute_atr_ratio(high: pd.Series, low: pd.Series,
                      close: pd.Series, period: int = 14) -> float:
    """
    Current ATR vs its own 20-day average.
    Ratio > 2.0 → volatility spike (HIGH_VOLATILITY regime signal).
    """
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_current = tr.rolling(period).mean()
    atr_avg     = atr_current.rolling(20).mean()
    ratio       = atr_current / atr_avg.replace(0, np.nan)
    v           = ratio.dropna()
    return round(float(v.iloc[-1]), 2) if not v.empty else 1.0


def slope(series: pd.Series, lookback: int = 5) -> float:
    """Linear regression slope over last N bars (normalised by mean price)."""
    s = series.dropna().iloc[-lookback:]
    if len(s) < 2:
        return 0.0
    x   = np.arange(len(s))
    m   = np.polyfit(x, s.values, 1)[0]
    avg = s.mean()
    return round(float(m / avg * 100), 4) if avg != 0 else 0.0   # % per bar


# ─────────────────────────────────────────────────────────────
# REGIME CLASSIFIER
# ─────────────────────────────────────────────────────────────

def classify_regime(ticker: str, history_days: int = 60) -> dict:
    """
    Fetches OHLCV data and classifies the current market regime
    for the given ticker using a multi-signal evidence scoring system.

    Returns a dict with:
        regime          : str  — one of the four regime constants
        regime_score    : dict — evidence scores for each regime
        adx             : float
        plus_di         : float
        minus_di        : float
        bb_width        : float
        atr_ratio       : float
        sma20_slope     : float  (% per bar)
        sma50_slope     : float  (% per bar)
        price_vs_sma20  : str   — ABOVE / BELOW
        price_vs_sma50  : str   — ABOVE / BELOW
        confidence      : float — winner score / total max score
        description     : str   — human-readable summary for LLM injection
    """
    try:
        df    = yf.Ticker(ticker).history(period=f"{history_days}d", interval="1d")
        if df.empty or len(df) < 30:
            return _regime_fallback(ticker, "Insufficient data")

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]

        # ── Compute all signals ───────────────────────────────
        adx, plus_di, minus_di = compute_adx(high, low, close)
        bb_width                = compute_bb_width(close)
        atr_ratio               = compute_atr_ratio(high, low, close)

        sma20       = close.rolling(20).mean()
        sma50       = close.rolling(50).mean()
        sma20_sl    = slope(sma20)
        sma50_sl    = slope(sma50, lookback=10)
        cur_price   = float(close.iloc[-1])
        sma20_last  = float(sma20.dropna().iloc[-1])
        sma50_last  = float(sma50.dropna().iloc[-1]) if len(sma50.dropna()) > 0 else sma20_last

        # MACD histogram (reuse existing helper from Cell 3)
        ema12      = close.ewm(span=12, adjust=False).mean()
        ema26      = close.ewm(span=26, adjust=False).mean()
        macd_hist  = float((ema12 - ema26 - (ema12 - ema26).ewm(span=9, adjust=False).mean()).iloc[-1])

        # RSI
        delta      = close.diff().dropna()
        gain       = delta.clip(lower=0).rolling(14).mean()
        loss       = (-delta.clip(upper=0)).rolling(14).mean()
        rs         = gain / loss.replace(0, np.nan)
        rsi        = float((100 - (100 / (1 + rs))).iloc[-1])

        above_sma20 = cur_price > sma20_last
        above_sma50 = cur_price > sma50_last

        # ── Evidence scoring ──────────────────────────────────
        # Each signal contributes 1 point to the matching regime(s).
        # Max possible score = 7 points per regime.
        scores = {
            REGIME_TRENDING_BULL   : 0,
            REGIME_TRENDING_BEAR   : 0,
            REGIME_RANGING         : 0,
            REGIME_HIGH_VOLATILITY : 0,
        }

        # Signal 1: ADX strength
        if adx > 25:
            if plus_di > minus_di:
                scores[REGIME_TRENDING_BULL] += 2
            else:
                scores[REGIME_TRENDING_BEAR] += 2
        elif adx < 20:
            scores[REGIME_RANGING] += 2

        # Signal 2: SMA20 positioning
        if above_sma20 and sma20_sl > 0:
            scores[REGIME_TRENDING_BULL] += 1
        elif not above_sma20 and sma20_sl < 0:
            scores[REGIME_TRENDING_BEAR] += 1
        else:
            scores[REGIME_RANGING] += 1

        # Signal 3: SMA50 positioning
        if above_sma50 and sma50_sl > 0:
            scores[REGIME_TRENDING_BULL] += 1
        elif not above_sma50 and sma50_sl < 0:
            scores[REGIME_TRENDING_BEAR] += 1
        else:
            scores[REGIME_RANGING] += 1

        # Signal 4: MACD histogram direction
        if macd_hist > 0:
            scores[REGIME_TRENDING_BULL] += 1
        else:
            scores[REGIME_TRENDING_BEAR] += 1

        # Signal 5: RSI zone
        if 45 <= rsi <= 75:
            scores[REGIME_TRENDING_BULL] += 1
        elif 25 <= rsi <= 55:
            scores[REGIME_TRENDING_BEAR] += 1
        elif 40 <= rsi <= 60:
            scores[REGIME_RANGING] += 1

        # Signal 6: ATR ratio (volatility spike)
        if atr_ratio >= 2.0:
            scores[REGIME_HIGH_VOLATILITY] += 3   # hard override weight
        elif atr_ratio >= 1.5:
            scores[REGIME_HIGH_VOLATILITY] += 2

        # Signal 7: Bollinger Band width (expansion = volatility)
        if bb_width >= 8.0:
            scores[REGIME_HIGH_VOLATILITY] += 2
        elif bb_width >= 5.0:
            scores[REGIME_HIGH_VOLATILITY] += 1
        elif bb_width <= 2.5:
            scores[REGIME_RANGING] += 1            # squeeze = ranging

        # ── Determine winner ──────────────────────────────────
        max_score = max(scores.values())
        winners   = [r for r, s in scores.items() if s == max_score]

        # Tie-break priority: HIGH_VOL > BEAR > RANGING > BULL
        # (always favour the more defensive classification)
        priority  = [
            REGIME_HIGH_VOLATILITY,
            REGIME_TRENDING_BEAR,
            REGIME_RANGING,
            REGIME_TRENDING_BULL,
        ]
        regime = next(r for r in priority if r in winners)

        # Regime confidence = winner score / theoretical max (9)
        regime_confidence = round(max_score / 9, 2)

        # ── Human-readable description for LLM injection ──────
        description = _build_regime_description(
            regime, adx, plus_di, minus_di, bb_width,
            atr_ratio, sma20_sl, above_sma20, above_sma50,
            macd_hist, rsi, scores, regime_confidence,
        )

        return {
            "regime"         : regime,
            "regime_score"   : scores,
            "adx"            : adx,
            "plus_di"        : plus_di,
            "minus_di"       : minus_di,
            "bb_width"       : bb_width,
            "atr_ratio"      : atr_ratio,
            "sma20_slope"    : sma20_sl,
            "sma50_slope"    : sma50_sl,
            "price_vs_sma20" : "ABOVE" if above_sma20 else "BELOW",
            "price_vs_sma50" : "ABOVE" if above_sma50 else "BELOW",
            "macd_hist"      : round(macd_hist, 4),
            "rsi"            : round(rsi, 2),
            "confidence"     : regime_confidence,
            "description"    : description,
            "error"          : None,
        }

    except Exception as e:
        return _regime_fallback(ticker, str(e))


def _build_regime_description(
    regime, adx, plus_di, minus_di, bb_width,
    atr_ratio, sma20_sl, above_sma20, above_sma50,
    macd_hist, rsi, scores, confidence,
) -> str:
    """Builds the natural-language block injected into the Market State Vector."""

    emoji = {
        REGIME_TRENDING_BULL   : "📈",
        REGIME_TRENDING_BEAR   : "📉",
        REGIME_RANGING         : "↔️",
        REGIME_HIGH_VOLATILITY : "⚡",
    }[regime]

    size_mult = REGIME_SIZE_MULTIPLIERS[regime]
    conf_pen  = REGIME_CONF_PENALTY[regime]
    suppress  = REGIME_SUPPRESSION.get(regime)

    lines = [
        f"--- MARKET REGIME ANALYSIS ---",
        f"Detected Regime : {emoji} {regime}  (confidence: {confidence:.0%})",
        f"ADX(14)         : {adx}  (+DI={plus_di}  -DI={minus_di})",
        f"BB Width        : {bb_width:.2f}%  |  ATR Ratio vs 20d avg: {atr_ratio:.2f}x",
        f"SMA20 Slope     : {sma20_sl:+.4f}%/bar  |  Price {'above' if above_sma20 else 'below'} SMA20",
        f"Price vs SMA50  : {'above' if above_sma50 else 'below'}",
        f"MACD Histogram  : {macd_hist:+.4f}  |  RSI: {rsi:.1f}",
        f"Evidence Scores : {scores}",
        f"",
        f"REGIME CONSTRAINTS FOR THIS DECISION:",
        f"  · Position size multiplier : {size_mult:.2f}× (applied to Kelly sizing)",
        f"  · Confidence threshold adj : +{conf_pen:.2f} (threshold raised in this regime)",
    ]

    if suppress:
        lines.append(
            f"  · ⛔ SUPPRESSED STANCE    : {suppress} signals are PROHIBITED "
            f"in {regime} — output HOLD instead"
        )
    else:
        lines.append(f"  · No stance suppression active")

    lines += [
        f"",
        f"REGIME GUIDANCE:",
    ]

    if regime == REGIME_TRENDING_BULL:
        lines += [
            f"  Strong uptrend confirmed by ADX, SMA alignment, and MACD.",
            f"  Favour BUY setups and trend continuation. Avoid short positions.",
            f"  Wider take-profit targets appropriate; tighten stops on weakness.",
        ]
    elif regime == REGIME_TRENDING_BEAR:
        lines += [
            f"  Downtrend confirmed. BUY signals are suppressed — do NOT go long.",
            f"  SELL (short) setups or HOLD are the only valid stances.",
            f"  Use tighter position sizing; bear markets have sharp counter-rallies.",
        ]
    elif regime == REGIME_RANGING:
        lines += [
            f"  Market lacks directional conviction (low ADX, tight Bollinger bands).",
            f"  Mean-reversion logic applies: buy near lower band, sell near upper.",
            f"  Avoid chasing breakouts — high false-signal rate in ranging markets.",
            f"  Reduce position size; take profits quickly.",
        ]
    elif regime == REGIME_HIGH_VOLATILITY:
        lines += [
            f"  Volatility spike detected (ATR ratio {atr_ratio:.2f}x or BB width {bb_width:.1f}%).",
            f"  Position sizes are severely reduced (0.40× multiplier).",
            f"  Widen stop-loss levels to avoid noise-driven exits.",
            f"  Only act on very high-confidence signals (threshold +0.10).",
        ]

    lines.append("------------------------------")
    return "\n".join(lines)


def _regime_fallback(ticker: str, reason: str) -> dict:
    """Returns a safe RANGING default when classification fails."""
    return {
        "regime"         : REGIME_RANGING,
        "regime_score"   : {},
        "adx"            : 0.0,
        "plus_di"        : 0.0,
        "minus_di"       : 0.0,
        "bb_width"       : 0.0,
        "atr_ratio"      : 1.0,
        "sma20_slope"    : 0.0,
        "sma50_slope"    : 0.0,
        "price_vs_sma20" : "UNKNOWN",
        "price_vs_sma50" : "UNKNOWN",
        "macd_hist"      : 0.0,
        "rsi"            : 50.0,
        "confidence"     : 0.0,
        "description"    : f"--- MARKET REGIME ANALYSIS ---\nRegime: RANGING (fallback — {reason})\n------------------------------",
        "error"          : reason,
    }


# ─────────────────────────────────────────────────────────────
# REGIME-AWARE SYSTEM PROMPT ADDON
# ─────────────────────────────────────────────────────────────
# This block is APPENDED to the existing SYSTEM_PROMPT in Cell 4
# dynamically per-call based on the detected regime.

def build_regime_system_addon(regime_data: dict) -> str:
    """
    Generates a regime-specific instruction block that is appended
    to the ATLAS system prompt before each LLM call.

    This keeps the base system prompt clean and unchanging while
    injecting regime-specific hard rules that ATLAS must follow.
    """
    regime    = regime_data["regime"]
    suppress  = REGIME_SUPPRESSION.get(regime)
    conf_pen  = REGIME_CONF_PENALTY[regime]
    size_mult = REGIME_SIZE_MULTIPLIERS[regime]

    lines = [
        "",
        "=== ACTIVE REGIME OVERRIDE INSTRUCTIONS ===",
        f"Current Market Regime: {regime}",
        f"These instructions OVERRIDE your general decision framework:",
        "",
    ]

    if suppress:
        lines += [
            f"⛔ HARD RULE: You MUST NOT output tactical_stance = \"{suppress}\".",
            f"   If your analysis suggests {suppress}, output \"HOLD\" instead.",
            f"   Reason: {suppress} signals are structurally suppressed in {regime}.",
            "",
        ]

    if conf_pen > 0:
        lines += [
            f"⚠️  CONFIDENCE RULE: Raise your internal bar. Only output BUY or SELL",
            f"   if your genuine conviction exceeds {0.65 + conf_pen:.2f} (normal threshold",
            f"   {0.65:.2f} + regime penalty {conf_pen:.2f}). When in doubt, output HOLD.",
            "",
        ]

    lines += [
        f"📐 SIZING NOTE: Position size will be automatically scaled by {size_mult:.2f}×",
        f"   by the execution engine. Your confidence_score drives the base size;",
        f"   the regime multiplier is applied externally — do not adjust for it.",
        "=== END REGIME OVERRIDE ===",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────

print("✅ Cell 10 — Market Regime Detection Layer loaded.")
print()
print("  Running smoke test on AAPL (uses live yfinance data)...")
_test = classify_regime("AAPL", history_days=60)
print(f"  Detected regime : {_test['regime']}  (confidence: {_test['confidence']:.0%})")
print(f"  ADX: {_test['adx']}  |  +DI: {_test['plus_di']}  |  -DI: {_test['minus_di']}")
print(f"  BB Width: {_test['bb_width']}%  |  ATR Ratio: {_test['atr_ratio']}x")
print(f"  SMA20 Slope: {_test['sma20_slope']:+.4f}%/bar")
print(f"  Evidence Scores: {_test['regime_score']}")
if _test['error']:
    print(f"  ⚠️  Warning: {_test['error']}")
print()
print("  Regime description preview (injected into Market State Vector):")
print()
print(_test['description'])


# ═════════════════════════════════════════════════════════════
# PATCH A — Cell 3: build_market_state_vector()
# ═════════════════════════════════════════════════════════════
#
# Add regime data injection into the Market State Vector.
# The function signature gains an optional `regime_data` param.
#
# FIND this line in Cell 3 (near the end of build_market_state_vector):
#
#     vector = f"""
#     === LIVE MARKET STATE VECTOR ===
#     ...
#     =================================
#     """
#     return vector.strip()
#
# REPLACE the return statement with:
#
#     # ── Inject regime block if provided ───────────────────
#     regime_block = regime_data.get("description", "") if regime_data else ""
#
#     vector = f"""
#     === LIVE MARKET STATE VECTOR ===
#     ... (all existing content unchanged) ...
#
#     {regime_block}
#     =================================
#     """
#     return vector.strip()
#
# AND update the function signature from:
#     def build_market_state_vector(ticker: str, history_days: int = 30) -> str:
# TO:
#     def build_market_state_vector(ticker: str, history_days: int = 30,
#                                   regime_data: dict = None) -> str:
#
# ═════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════
# PATCH B — Cell 4: get_ai_decision()
# ═════════════════════════════════════════════════════════════
#
# Update get_ai_decision() to accept and append the regime system addon.
#
# FIND the function signature:
#     def get_ai_decision(market_state_vector, ticker, memory_block=None):
#
# REPLACE WITH:
#     def get_ai_decision(market_state_vector, ticker,
#                         memory_block=None, regime_data=None):
#
# FIND this line inside get_ai_decision():
#     response = client.messages.create(
#         model=CONFIG["model"],
#         max_tokens=800,
#         system=SYSTEM_PROMPT,
#         ...
#     )
#
# REPLACE WITH:
#     # Build dynamic system prompt with regime addon
#     regime_addon   = build_regime_system_addon(regime_data) if regime_data else ""
#     dynamic_system = SYSTEM_PROMPT + regime_addon
#
#     response = client.messages.create(
#         model=CONFIG["model"],
#         max_tokens=800,
#         system=dynamic_system,      # ← was: SYSTEM_PROMPT
#         ...
#     )
#
# ═════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════
# PATCH C — Cell 6: run_trading_loop()
# ═════════════════════════════════════════════════════════════
#
# Four targeted changes inside the per-ticker analysis loop.
#
# ── CHANGE 1: After "vector = build_market_state_vector(...)" ──
#
# FIND:
#     vector = build_market_state_vector(
#         ticker,
#         history_days=CONFIG["price_history_days"]
#     )
#
# REPLACE WITH:
#     # Classify regime first
#     regime_data = classify_regime(ticker, history_days=60)
#     regime      = regime_data["regime"]
#     print(f"  🧭 Regime: {regime}  (conf: {regime_data['confidence']:.0%}  "
#           f"ADX: {regime_data['adx']}  BB Width: {regime_data['bb_width']}%)")
#
#     vector = build_market_state_vector(
#         ticker,
#         history_days=CONFIG["price_history_days"],
#         regime_data=regime_data,           # ← inject regime into vector
#     )
#
# ── CHANGE 2: Pass regime_data to get_ai_decision() ───────────
#
# FIND:
#     result = get_ai_decision(vector, ticker, memory_block=memory_block)
#
# REPLACE WITH:
#     result = get_ai_decision(
#         vector, ticker,
#         memory_block=memory_block,
#         regime_data=regime_data,           # ← new param
#     )
#
# ── CHANGE 3: Stance suppression check ────────────────────────
#
# FIND (after decision is parsed, before open_position call):
#     if stance in ("BUY", "SELL") and confidence >= conf_threshold:
#
# REPLACE WITH:
#     # ── Regime stance suppression ─────────────────────────
#     suppressed_stance = REGIME_SUPPRESSION.get(regime)
#     if suppressed_stance and stance == suppressed_stance:
#         print(f"  ⛔ [{regime}] {stance} stance suppressed → forced HOLD.")
#         stance = "HOLD"
#
#     # ── Regime confidence threshold adjustment ─────────────
#     regime_conf_threshold = conf_threshold + REGIME_CONF_PENALTY.get(regime, 0)
#
#     if stance in ("BUY", "SELL") and confidence >= regime_conf_threshold:
#
# ── CHANGE 4: Apply regime size multiplier inside open_position ─
#
# FIND (inside compute_position_size call or just before open_position):
#     portfolio.open_position(
#         ticker          = ticker,
#         stance          = stance,
#         current_price   = cur_price,
#         stop_loss_pct   = sl_pct,
#         take_profit_pct = tp_pct,
#         confidence      = confidence,
#         rationale       = rationale,
#         current_prices  = current_prices,
#     )
#
# REPLACE WITH:
#     # Regime multiplier applied to Kelly-sized notional via confidence scaling.
#     # We encode it as a confidence dampener so the existing sizing math handles it.
#     regime_mult      = REGIME_SIZE_MULTIPLIERS.get(regime, 1.0)
#     adjusted_conf    = round(confidence * regime_mult, 4)
#
#     portfolio.open_position(
#         ticker          = ticker,
#         stance          = stance,
#         current_price   = cur_price,
#         stop_loss_pct   = sl_pct,
#         take_profit_pct = tp_pct,
#         confidence      = adjusted_conf,   # ← regime-dampened confidence
#         rationale       = f"[{regime}] {rationale}",
#         current_prices  = current_prices,
#     )
#
# ═════════════════════════════════════════════════════════════
PATCH_C_SUMMARY = """
✅ Patch C summary — Cell 6 changes:
  1. classify_regime() called per-ticker before build_market_state_vector()
  2. regime_data passed to get_ai_decision() → dynamic system prompt addon
  3. Stance suppression: BUY blocked in TRENDING_BEAR, SELL in TRENDING_BULL
  4. Confidence threshold raised by regime penalty before trade gate check
  5. Regime size multiplier encoded as confidence dampener into open_position()
"""
print(PATCH_C_SUMMARY)
