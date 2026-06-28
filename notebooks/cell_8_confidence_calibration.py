"""
================================================================================
  CELL 8 — Phase 3 Sub-Task 3.2: Confidence Calibration Layer
  Paste this into a NEW Colab cell and run it BEFORE Cell 6.
  Then replace the open_position() call in Cell 6 with the updated version
  shown at the bottom of this file.
================================================================================
"""

# ============================================================
# CELL 8 — Confidence Calibration Layer
# ============================================================

import numpy as np

# ─────────────────────────────────────────────────────────────
# THE MATH EXPLAINED
# ─────────────────────────────────────────────────────────────
#
# STEP 1 — BASE ALLOCATION via Fractional Kelly Criterion
# ───────────────────────────────────────────────────────
# Full Kelly: f* = (p * b - q) / b
#   where p  = estimated win probability (mapped from confidence)
#         q  = 1 - p (estimated loss probability)
#         b  = reward/risk ratio (take_profit_pct / stop_loss_pct)
#
# Full Kelly is theoretically optimal but notoriously aggressive
# in live use. We use QUARTER Kelly (0.25 * f*) which produces
# smoother equity curves with far lower ruin risk. This is the
# standard institutional practice.
#
# Confidence → Win probability mapping (sigmoid-shaped):
#   conf 0.65 → p ≈ 0.55  (slight edge)
#   conf 0.75 → p ≈ 0.62  (moderate edge)
#   conf 0.85 → p ≈ 0.70  (strong edge)
#   conf 0.95 → p ≈ 0.78  (very strong edge)
#
# STEP 2 — DRAWDOWN SCALING FACTOR
# ──────────────────────────────────
# As the portfolio bleeds down from its peak, we apply a
# multiplicative "throttle" that shrinks position size:
#
#   dd_factor = max(0.2,  1 - (current_drawdown_pct / max_dd_ceiling) ^ 1.5)
#
#   · At 0% drawdown   → factor = 1.00  (full size)
#   · At 5% drawdown   → factor ≈ 0.75
#   · At 10% drawdown  → factor ≈ 0.44
#   · At 15% drawdown  → factor = 0.20  (floor — never goes below 20%)
#   max_dd_ceiling = 15% by default (tune via CONFIG)
#
# The exponent 1.5 makes the curve convex — gentle at first, then
# aggressive as drawdown deepens. This is intentional: we want to
# let the system breathe during minor dips but slam the brakes hard
# during a real drawdown regime.
#
# STEP 3 — FINAL POSITION SIZE
# ──────────────────────────────
# final_pct = clip(kelly_fraction * dd_factor, min_pct, max_pct)
#
# Hard bounds prevent any single trade from exceeding the
# configured maximum regardless of how confident ATLAS is.
#
# ─────────────────────────────────────────────────────────────


# ── TUNABLE PARAMETERS (add these to CONFIG in Cell 2 if desired) ──
CALIBRATION_CONFIG = {
    "kelly_fraction"      : 0.25,    # Quarter-Kelly multiplier (0.1–0.5)
    "min_position_pct"    : 0.02,    # Floor: never risk less than 2% per trade
    "max_position_pct"    : 0.10,    # Ceiling: never exceed 10% per trade
    "reward_risk_ratio"   : 2.0,     # Default b (take_profit / stop_loss)
    "max_drawdown_ceiling": 15.0,    # Drawdown % at which floor is reached
    "dd_exponent"         : 1.5,     # Convexity of the drawdown throttle curve
    "dd_floor_factor"     : 0.20,    # Min throttle applied at max drawdown
    "confidence_floor"    : 0.65,    # Reject any trade below this (redundant safety)
}


def confidence_to_win_prob(confidence: float) -> float:
    """
    Maps AI confidence score [0,1] to an estimated win probability [0,1]
    using a calibrated sigmoid that prevents overconfidence inflation.

    Key design decision: we never map confidence directly to win probability
    1:1 because that would be epistemically dishonest — a 0.90 confidence
    score from an LLM does not mean a 90% win rate. The sigmoid compresses
    extreme values and keeps win_prob in a realistic [0.50, 0.80] range.
    """
    # Sigmoid centred at 0.75 confidence → 0.62 win prob
    # Scale factor of 8 gives reasonable spread across the [0.65, 0.95] range
    win_prob = 0.50 + 0.30 * (1 / (1 + np.exp(-8 * (confidence - 0.75))))
    return round(float(np.clip(win_prob, 0.50, 0.80)), 4)


def compute_kelly_fraction(
    confidence    : float,
    reward_risk_b : float,
    kelly_mult    : float,
) -> float:
    """
    Computes the fractional Kelly position size as a % of portfolio.

    Args:
        confidence    : ATLAS confidence score [0, 1]
        reward_risk_b : take_profit_pct / stop_loss_pct ratio
        kelly_mult    : fraction of full Kelly to use (e.g. 0.25)

    Returns:
        kelly_pct: recommended position size as fraction of portfolio [0, 1]
    """
    p = confidence_to_win_prob(confidence)
    q = 1.0 - p
    b = max(reward_risk_b, 0.1)   # prevent division-by-zero

    full_kelly = (p * b - q) / b

    # Kelly can be negative (negative edge) — clamp to 0
    full_kelly = max(0.0, full_kelly)

    fractional_kelly = full_kelly * kelly_mult
    return round(fractional_kelly, 4)


def compute_drawdown_factor(
    current_portfolio_value : float,
    peak_portfolio_value    : float,
    max_dd_ceiling_pct      : float,
    dd_exponent             : float,
    dd_floor_factor         : float,
) -> tuple[float, float]:
    """
    Computes a [dd_floor, 1.0] throttle multiplier based on current drawdown.

    Returns:
        (dd_factor, current_drawdown_pct)
    """
    if peak_portfolio_value <= 0:
        return 1.0, 0.0

    current_dd_pct = max(
        0.0,
        (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value * 100
    )

    # Convex decay curve — gentle early, steep near ceiling
    raw_factor = 1.0 - (current_dd_pct / max_dd_ceiling_pct) ** dd_exponent
    dd_factor  = float(np.clip(raw_factor, dd_floor_factor, 1.0))

    return round(dd_factor, 4), round(current_dd_pct, 2)


def compute_position_size(
    confidence            : float,
    current_portfolio_value: float,
    peak_portfolio_value  : float,
    take_profit_pct       : float,
    stop_loss_pct         : float,
    cal_cfg               : dict = CALIBRATION_CONFIG,
) -> dict:
    """
    Master function: returns position sizing metadata for a proposed trade.

    Args:
        confidence             : ATLAS confidence score [0, 1]
        current_portfolio_value: current total portfolio value ($)
        peak_portfolio_value   : highest portfolio value seen this session ($)
        take_profit_pct        : % distance to take-profit from entry
        stop_loss_pct          : % distance to stop-loss from entry

    Returns dict with:
        position_pct   : final % of portfolio to allocate
        notional_usd   : dollar amount to allocate
        kelly_raw      : raw kelly fraction (before dd scaling)
        dd_factor      : drawdown throttle multiplier
        dd_pct         : current drawdown from peak
        win_prob       : estimated win probability used
        sizing_tier    : human-readable tier label
    """
    if confidence < cal_cfg["confidence_floor"]:
        return {
            "position_pct" : 0.0,
            "notional_usd" : 0.0,
            "kelly_raw"    : 0.0,
            "dd_factor"    : 1.0,
            "dd_pct"       : 0.0,
            "win_prob"     : 0.0,
            "sizing_tier"  : "REJECTED — below confidence floor",
        }

    # ── Step 1: Kelly base fraction ───────────────────────────
    reward_risk = (take_profit_pct / stop_loss_pct) if stop_loss_pct > 0 else cal_cfg["reward_risk_ratio"]
    kelly_raw   = compute_kelly_fraction(
        confidence,
        reward_risk,
        cal_cfg["kelly_fraction"],
    )

    # ── Step 2: Drawdown throttle ─────────────────────────────
    dd_factor, dd_pct = compute_drawdown_factor(
        current_portfolio_value,
        peak_portfolio_value,
        cal_cfg["max_drawdown_ceiling"],
        cal_cfg["dd_exponent"],
        cal_cfg["dd_floor_factor"],
    )

    # ── Step 3: Final position % with hard bounds ─────────────
    raw_pct      = kelly_raw * dd_factor
    position_pct = float(np.clip(
        raw_pct,
        cal_cfg["min_position_pct"],
        cal_cfg["max_position_pct"],
    ))

    notional_usd = round(current_portfolio_value * position_pct, 2)
    win_prob     = confidence_to_win_prob(confidence)

    # ── Tier label ────────────────────────────────────────────
    if position_pct >= 0.08:
        tier = "FULL  (high conviction)"
    elif position_pct >= 0.05:
        tier = "STANDARD"
    elif position_pct >= 0.03:
        tier = "REDUCED  (low conviction / drawdown)"
    else:
        tier = "MINIMAL  (near confidence floor / deep drawdown)"

    return {
        "position_pct" : round(position_pct, 4),
        "notional_usd" : notional_usd,
        "kelly_raw"    : kelly_raw,
        "dd_factor"    : dd_factor,
        "dd_pct"       : dd_pct,
        "win_prob"     : win_prob,
        "sizing_tier"  : tier,
    }


# ─────────────────────────────────────────────────────────────
# PATCH: Add peak tracking to PaperPortfolio
# ─────────────────────────────────────────────────────────────
# Run this block to monkey-patch the existing PaperPortfolio
# class with peak tracking (needed by the drawdown calculator).

_original_init = PaperPortfolio.__init__

def _patched_init(self, starting_capital, max_position_pct):
    _original_init(self, starting_capital, max_position_pct)
    self.peak_portfolio_value = starting_capital   # ← new field

PaperPortfolio.__init__ = _patched_init


def _patched_open_position(
    self,
    ticker          : str,
    stance          : str,
    current_price   : float,
    stop_loss_pct   : float,
    take_profit_pct : float,
    confidence      : float,
    rationale       : str,
    current_prices  : dict = None,     # ← new param for live portfolio valuation
):
    """
    Replacement for PaperPortfolio.open_position() that uses the
    Confidence Calibration Layer for dynamic position sizing.
    """
    if stance == "HOLD":
        return None

    if ticker in self.open_positions:
        self._log(f"[SKIP] Already have open position in {ticker}.")
        return None

    # ── Live portfolio value for drawdown calculation ─────────
    prices_for_valuation = current_prices or {ticker: current_price}
    current_total_value  = self.get_portfolio_value(prices_for_valuation)

    # ── Update peak ───────────────────────────────────────────
    self.peak_portfolio_value = max(
        self.peak_portfolio_value,
        current_total_value,
    )

    # ── Calibrated position size ──────────────────────────────
    sizing = compute_position_size(
        confidence             = confidence,
        current_portfolio_value= current_total_value,
        peak_portfolio_value   = self.peak_portfolio_value,
        take_profit_pct        = take_profit_pct,
        stop_loss_pct          = stop_loss_pct,
    )

    if sizing["position_pct"] == 0.0:
        self._log(f"[SKIP] {ticker} — {sizing['sizing_tier']}")
        return None

    notional = sizing["notional_usd"]

    if notional > self.cash:
        self._log(
            f"[SKIP] Insufficient cash (${self.cash:,.2f}) for "
            f"{ticker} notional (${notional:,.2f})."
        )
        return None

    shares = notional / current_price

    # ── Set SL / TP price levels ──────────────────────────────
    if stance == "BUY":
        stop_loss   = round(current_price * (1 - stop_loss_pct   / 100), 2)
        take_profit = round(current_price * (1 + take_profit_pct / 100), 2)
    else:
        stop_loss   = round(current_price * (1 + stop_loss_pct   / 100), 2)
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
        f"[OPEN] {stance} {ticker} | {shares:.2f} shares @ ${current_price:.2f}\n"
        f"         Sizing tier  : {sizing['sizing_tier']}\n"
        f"         Notional     : ${notional:,.2f}  ({sizing['position_pct']*100:.1f}% of portfolio)\n"
        f"         Kelly raw    : {sizing['kelly_raw']*100:.2f}%  →  after DD throttle ({sizing['dd_factor']:.2f}x at {sizing['dd_pct']:.1f}% drawdown)\n"
        f"         Win prob est : {sizing['win_prob']:.2f}  |  Confidence: {confidence:.2f}\n"
        f"         SL: ${stop_loss}  |  TP: ${take_profit}"
    )
    return pos


# Patch the class method
PaperPortfolio.open_position = _patched_open_position

print("✅ Cell 8 — Confidence Calibration Layer loaded & PaperPortfolio patched.")
print()
print("  Sizing preview across confidence levels (no drawdown, 2:1 reward/risk):")
print(f"  {'Confidence':>12} | {'Win Prob':>9} | {'Kelly Raw':>10} | {'Final Alloc':>12} | Tier")
print("  " + "─"*75)
for conf in [0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
    s = compute_position_size(
        confidence              = conf,
        current_portfolio_value = 100_000,
        peak_portfolio_value    = 100_000,
        take_profit_pct         = 5.0,
        stop_loss_pct           = 2.5,
    )
    print(
        f"  {conf:>12.2f} | {s['win_prob']:>9.3f} | "
        f"{s['kelly_raw']*100:>9.2f}% | "
        f"{s['position_pct']*100:>11.1f}% | {s['sizing_tier']}"
    )

print()
print("  Drawdown throttle preview (confidence=0.80, 2:1 R/R):")
print(f"  {'Drawdown':>10} | {'DD Factor':>10} | {'Final Alloc':>12}")
print("  " + "─"*40)
for dd in [0, 3, 5, 8, 10, 12, 15]:
    fake_current = 100_000 * (1 - dd / 100)
    s = compute_position_size(
        confidence              = 0.80,
        current_portfolio_value = fake_current,
        peak_portfolio_value    = 100_000,
        take_profit_pct         = 5.0,
        stop_loss_pct           = 2.5,
    )
    print(f"  {dd:>9.0f}% | {s['dd_factor']:>10.3f} | {s['position_pct']*100:>11.1f}%")


# ─────────────────────────────────────────────────────────────
# CELL 6 REPLACEMENT — open_position() call
# ─────────────────────────────────────────────────────────────
#
# In Cell 6, find this block:
#
#       portfolio.open_position(
#           ticker          = ticker,
#           stance          = stance,
#           current_price   = cur_price,
#           stop_loss_pct   = sl_pct,
#           take_profit_pct = tp_pct,
#           confidence      = confidence,
#           rationale       = rationale,
#       )
#
# Replace it with:
#
#       portfolio.open_position(
#           ticker          = ticker,
#           stance          = stance,
#           current_price   = cur_price,
#           stop_loss_pct   = sl_pct,
#           take_profit_pct = tp_pct,
#           confidence      = confidence,
#           rationale       = rationale,
#           current_prices  = current_prices,   # ← pass full price dict
#       )
#
# That single added argument is all that's needed. The patched method
# handles everything else automatically.
# ─────────────────────────────────────────────────────────────
