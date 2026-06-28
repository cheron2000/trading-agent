"""
================================================================================
  CELL 9 — Phase 3 Sub-Task 3.3: Context Memory Injection
  Paste this into Colab Cell 9 and run it AFTER Cell 8, BEFORE Cell 6.
  Then apply the two targeted patches shown at the bottom to Cell 4 and Cell 6.
================================================================================

  ARCHITECTURE OVERVIEW
  ─────────────────────
  The memory pipeline has three stages:

  ┌──────────────────────────────────────────────────────────┐
  │  STAGE 1 — RECORD                                        │
  │  After every ATLAS decision, a MemoryEntry is created    │
  │  and pushed into the DecisionMemoryBuffer (ring buffer). │
  └───────────────────────┬──────────────────────────────────┘
                          │
  ┌───────────────────────▼──────────────────────────────────┐
  │  STAGE 2 — ENRICH                                        │
  │  At the start of each cycle, open positions are          │
  │  retrospectively updated with live PnL and outcome tags. │
  └───────────────────────┬──────────────────────────────────┘
                          │
  ┌───────────────────────▼──────────────────────────────────┐
  │  STAGE 3 — INJECT                                        │
  │  The buffer is serialised to a compact natural-language  │
  │  block and appended to the Market State Vector before    │
  │  it reaches the LLM. ATLAS sees its own history.         │
  └──────────────────────────────────────────────────────────┘

  WHY NATURAL LANGUAGE OVER RAW JSON FOR THE MEMORY BLOCK?
  ─────────────────────────────────────────────────────────
  LLMs parse structured prose more reliably inside a larger
  context than embedded JSON objects, which compete visually
  with the system prompt's own JSON output schema and can
  cause the model to confuse input structure with output
  format. The memory block uses a telegraph-style format
  that is dense but unambiguous.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────
# DATA STRUCTURE
# ─────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """
    A single record written to the buffer after each ATLAS decision.
    Fields are split into two groups:

    · Immutable at write time  — set when the decision arrives.
    · Mutable retrospectively  — updated as the position evolves
                                  or closes across future cycles.
    """
    # ── Written at decision time ──────────────────────────────
    cycle           : int
    timestamp       : str           # ISO UTC
    ticker          : str
    stance          : str           # BUY | SELL | HOLD
    confidence      : float
    rationale       : str           # ATLAS's own 3-sentence rationale
    entry_price     : Optional[float]
    stop_loss       : Optional[float]
    take_profit     : Optional[float]
    momentum_signal : str
    volume_signal   : str
    sentiment_signal: str

    # ── Updated retrospectively ───────────────────────────────
    current_price   : Optional[float] = None
    unrealised_pnl  : Optional[float] = None   # USD
    unrealised_pct  : Optional[float] = None   # %
    outcome         : str = "OPEN"             # OPEN | WIN | LOSS | HOLD_SKIP
    close_reason    : Optional[str] = None     # TAKE_PROFIT | STOP_LOSS | REVERSAL
    exit_price      : Optional[float] = None
    realised_pnl    : Optional[float] = None   # USD, set on close

    def update_live(self, current_price: float):
        """Refreshes mark-to-market fields for an open position."""
        if self.entry_price is None or self.stance == "HOLD":
            return
        self.current_price = current_price
        if self.stance == "BUY":
            pnl = (current_price - self.entry_price)
        else:  # SHORT
            pnl = (self.entry_price - current_price)

        # We don't have shares here — express as % move instead
        self.unrealised_pct = round((pnl / self.entry_price) * 100, 2)
        self.unrealised_pnl = None   # dollar PnL needs shares; use % in memory

    def mark_closed(self, exit_price: float, realised_pnl: float, reason: str):
        """Finalises a closed trade inside the memory entry."""
        self.exit_price   = exit_price
        self.realised_pnl = round(realised_pnl, 2)
        self.close_reason = reason
        self.outcome      = "WIN" if realised_pnl > 0 else "LOSS"
        self.current_price = exit_price


# ─────────────────────────────────────────────────────────────
# RING BUFFER
# ─────────────────────────────────────────────────────────────

class DecisionMemoryBuffer:
    """
    Fixed-size ring buffer of MemoryEntry objects, one per
    ATLAS decision (across all tickers, all cycles).

    Design decisions:
    · Ring buffer (deque with maxlen) — O(1) append, automatic
      eviction of oldest entries. No memory leak in long sessions.
    · Keyed index (ticker → entry) — allows O(1) retrospective
      updates when a position's live price or outcome changes,
      without scanning the entire buffer.
    · Per-ticker history — serialise() can emit ticker-scoped
      sections so ATLAS sees its own decision trail per asset.
    """

    def __init__(self, maxlen: int = 20):
        """
        Args:
            maxlen: maximum number of decision records to retain.
                    At 5 assets × 5 cycles, 20 covers one full session.
                    Increase to 50 for multi-hour runs.
        """
        self._buffer   : deque[MemoryEntry]       = deque(maxlen=maxlen)
        self._index    : dict[str, MemoryEntry]   = {}  # ticker → most recent entry
        self.maxlen    = maxlen

    # ── Write ─────────────────────────────────────────────────

    def record(self, entry: MemoryEntry):
        """Pushes a new decision into the buffer and updates the index."""
        self._buffer.append(entry)
        self._index[entry.ticker] = entry   # always points to most recent

    # ── Retrospective Update ──────────────────────────────────

    def update_live_prices(self, current_prices: dict[str, float]):
        """
        Called at the top of every cycle. Refreshes unrealised PnL
        for all entries that still have OPEN positions.
        """
        for entry in self._buffer:
            if entry.outcome == "OPEN" and entry.ticker in current_prices:
                entry.update_live(current_prices[entry.ticker])

    def mark_trade_closed(
        self,
        ticker      : str,
        exit_price  : float,
        realised_pnl: float,
        reason      : str,
    ):
        """
        Called by the trading loop when a ClosedTrade event fires.
        Updates the most recent memory entry for that ticker.
        """
        entry = self._index.get(ticker)
        if entry and entry.outcome == "OPEN":
            entry.mark_closed(exit_price, realised_pnl, reason)

    # ── Serialise ─────────────────────────────────────────────

    def serialise(self, for_ticker: Optional[str] = None) -> str:
        """
        Converts the buffer into a compact natural-language block
        ready for injection into the Market State Vector.

        Args:
            for_ticker: if supplied, the output starts with a
                        dedicated "RECENT DECISIONS FOR <TICKER>"
                        section before the cross-asset history.
                        This helps ATLAS weight same-asset history
                        more heavily when reasoning about that asset.

        Format per entry (telegraph style):
            [CYC-N | TIMESTAMP] TICKER · STANCE (conf=X.XX)
            Status  : OPEN +2.3% unreal  |  Entry $X  SL $X  TP $X
            Signals : MOM=BULLISH VOL=CONFIRMING SENT=POSITIVE
            Rationale: <ATLAS's own words, truncated to 120 chars>
        """
        if not self._buffer:
            return "  [No prior decisions in memory buffer]"

        lines = []

        # ── Section A: Same-ticker history (most relevant) ────
        if for_ticker:
            ticker_entries = [e for e in self._buffer if e.ticker == for_ticker]
            if ticker_entries:
                lines.append(f"  -- RECENT DECISIONS FOR {for_ticker} --")
                for e in reversed(ticker_entries):   # newest first
                    lines.extend(self._format_entry(e, highlight=True))
                lines.append("")

        # ── Section B: Full cross-asset history ───────────────
        lines.append("  -- FULL DECISION HISTORY (newest first) --")
        for e in reversed(self._buffer):
            lines.extend(self._format_entry(e, highlight=False))

        return "\n".join(lines)

    def _format_entry(self, e: MemoryEntry, highlight: bool) -> list[str]:
        """Formats a single MemoryEntry into 4 compact lines."""
        prefix = "►" if highlight else " "

        # Header line
        ts_short = e.timestamp[:16].replace("T", " ")
        header = (
            f"  {prefix} [CYC-{e.cycle} | {ts_short}] "
            f"{e.ticker} · {e.stance} (conf={e.confidence:.2f})"
        )

        # Status line
        if e.stance == "HOLD":
            status = f"    Status  : HOLD — no position opened"
        elif e.outcome == "OPEN":
            pnl_str = (
                f"{e.unrealised_pct:+.2f}% unreal"
                if e.unrealised_pct is not None else "unreal P&L pending"
            )
            status = (
                f"    Status  : OPEN {pnl_str}"
                f"  |  Entry ${e.entry_price}  "
                f"SL ${e.stop_loss}  TP ${e.take_profit}"
            )
        else:
            pnl_str = (
                f"${e.realised_pnl:+,.2f}"
                if e.realised_pnl is not None else "PnL N/A"
            )
            icon = "✓ WIN" if e.outcome == "WIN" else "✗ LOSS"
            status = (
                f"    Status  : {icon} {pnl_str}"
                f"  |  Exit ${e.exit_price}  Reason: {e.close_reason}"
            )

        # Signal line
        signals = (
            f"    Signals : MOM={e.momentum_signal} "
            f"VOL={e.volume_signal} "
            f"SENT={e.sentiment_signal}"
        )

        # Rationale (truncated — LLM already generated it; keep brief)
        rationale_short = (e.rationale[:117] + "...") if len(e.rationale) > 120 else e.rationale
        rationale_line  = f"    Rationale: {rationale_short}"

        return [header, status, signals, rationale_line, ""]

    # ── Convenience ───────────────────────────────────────────

    def __len__(self):
        return len(self._buffer)

    def recent_stance_for(self, ticker: str) -> Optional[str]:
        """Quick lookup: what was ATLAS's last stance on this ticker?"""
        entry = self._index.get(ticker)
        return entry.stance if entry else None

    def consecutive_same_stance(self, ticker: str, stance: str) -> int:
        """
        Counts how many consecutive recent decisions for a ticker
        share the same stance. Used by the loop to flag potential
        confirmation bias in ATLAS's reasoning.
        """
        count = 0
        for e in reversed(self._buffer):
            if e.ticker == ticker:
                if e.stance == stance:
                    count += 1
                else:
                    break
        return count


# ─────────────────────────────────────────────────────────────
# GLOBAL BUFFER INSTANCE
# Instantiated once here; imported by Cells 4 and 6 by reference.
# ─────────────────────────────────────────────────────────────

atlas_memory = DecisionMemoryBuffer(maxlen=20)

print("✅ Cell 9 — DecisionMemoryBuffer initialised (maxlen=20).")
print(f"   Buffer slots: {atlas_memory.maxlen}  |  Entries so far: {len(atlas_memory)}")
print()

# Quick smoke test
_test_entry = MemoryEntry(
    cycle=0, timestamp="2025-01-01T00:00:00", ticker="TEST",
    stance="BUY", confidence=0.82, rationale="Test rationale for smoke test.",
    entry_price=100.0, stop_loss=97.5, take_profit=105.0,
    momentum_signal="BULLISH", volume_signal="CONFIRMING", sentiment_signal="POSITIVE",
)
atlas_memory.record(_test_entry)
print("  Smoke-test serialisation:")
print(atlas_memory.serialise(for_ticker="TEST"))
atlas_memory._buffer.clear()
atlas_memory._index.clear()
print("  Buffer cleared after smoke test. Ready for live use.")


# ═════════════════════════════════════════════════════════════
# PATCH A — Cell 4: get_ai_decision()
# ═════════════════════════════════════════════════════════════
#
# Replace your existing get_ai_decision() function in Cell 4
# with the version below. The only additions are:
#   1. Accept a `memory_block` parameter (str | None).
#   2. Inject it into the user message before the vector.
#
# The system prompt in Cell 4 is UNCHANGED.
# ═════════════════════════════════════════════════════════════

def get_ai_decision(
    market_state_vector : str,
    ticker              : str,
    memory_block        : Optional[str] = None,    # ← NEW PARAM
) -> dict:
    """
    Sends the Market State Vector (+ optional memory block) to Claude
    and returns a parsed tactical decision dictionary.
    """
    # ── Build memory section ──────────────────────────────────
    memory_section = ""
    if memory_block and memory_block.strip():
        memory_section = f"""
=== ATLAS DECISION MEMORY (your prior decisions — use for consistency) ===
{memory_block}
=== END MEMORY ===
"""

    user_message = f"""
Analyse the following live Market State Vector and output your tactical decision
in strict JSON format per your system instructions.

{memory_section}
{market_state_vector}

Asset under analysis: {ticker}

MEMORY GUIDANCE: If the memory block above shows recent decisions for {ticker},
weigh them carefully:
  · Avoid reversing a position without a materially changed signal.
  · If the same stance appears 3+ consecutive cycles, scrutinise whether
    you are exhibiting confirmation bias or the trend genuinely persists.
  · A HOLD decision preceded by an open position means the position stays open.

Respond with JSON only.
"""

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
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$",        "", raw_text)

        decision = json.loads(raw_text)

        required_keys = {
            "asset", "tactical_stance", "confidence_score",
            "rationale", "execution_parameters", "signal_breakdown",
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


print("✅ Patch A applied — get_ai_decision() now accepts memory_block param.")


# ═════════════════════════════════════════════════════════════
# PATCH B — Cell 6: Trading Loop integration
# ═════════════════════════════════════════════════════════════
#
# Three targeted replacements inside run_trading_loop().
# Each is labelled with its location in the existing Cell 6 code.
# ═════════════════════════════════════════════════════════════

PATCH_B_INSTRUCTIONS = """
──────────────────────────────────────────────────────────────
PATCH B  ·  Three changes to Cell 6 (run_trading_loop)
──────────────────────────────────────────────────────────────

CHANGE 1 of 3 — Top of the cycle loop, after current_prices fetch.
Location: just before "STEP 2: Check stop-loss / take-profit exits"

ADD these two lines:

    # ── Refresh memory with live prices ───────────────────────
    atlas_memory.update_live_prices(current_prices)

────────────────────────────────────────────────────────────

CHANGE 2 of 3 — Inside check_exit_conditions block.
Location: replace the existing exits-handling block:

    exits = portfolio.check_exit_conditions(current_prices)
    if exits:
        print(f"  ⚡ {len(exits)} position(s) auto-closed by SL/TP rules.")

REPLACE WITH:

    exits = portfolio.check_exit_conditions(current_prices)
    for closed_trade in exits:
        if closed_trade:
            atlas_memory.mark_trade_closed(
                ticker       = closed_trade.ticker,
                exit_price   = closed_trade.exit_price,
                realised_pnl = closed_trade.pnl_usd,
                reason       = closed_trade.close_reason,
            )
    if exits:
        print(f"  ⚡ {len(exits)} position(s) auto-closed by SL/TP rules.")

────────────────────────────────────────────────────────────

CHANGE 3 of 3 — Inside the per-ticker analysis loop.
Location: replace the get_ai_decision() call and the
          portfolio.open_position() call.

FIND:
    result = get_ai_decision(vector, ticker)

REPLACE WITH:
    memory_block = atlas_memory.serialise(for_ticker=ticker)
    result = get_ai_decision(vector, ticker, memory_block=memory_block)

Then, AFTER the successful decision block where you call
portfolio.open_position(), ADD the memory record call.
Find the open_position() call and ADD AFTER it:

    # ── Record decision in memory ──────────────────────────────
    signals = decision.get("signal_breakdown", {})
    atlas_memory.record(MemoryEntry(
        cycle            = cycle,
        timestamp        = datetime.now(timezone.utc).isoformat(),
        ticker           = ticker,
        stance           = stance,
        confidence       = confidence,
        rationale        = rationale,
        entry_price      = cur_price if stance != "HOLD" else None,
        stop_loss        = portfolio.open_positions[ticker].stop_loss
                           if ticker in portfolio.open_positions else None,
        take_profit      = portfolio.open_positions[ticker].take_profit
                           if ticker in portfolio.open_positions else None,
        momentum_signal  = signals.get("momentum_signal", "NEUTRAL"),
        volume_signal    = signals.get("volume_signal",   "WEAK"),
        sentiment_signal = signals.get("sentiment_signal","NEUTRAL"),
    ))

    # ── Bias detection warning ────────────────────────────────
    streak = atlas_memory.consecutive_same_stance(ticker, stance)
    if streak >= 3:
        print(
            f"  ⚠️  BIAS ALERT: ATLAS has chosen {stance} on {ticker} "
            f"{streak} consecutive cycles. Verify signal independence."
        )

──────────────────────────────────────────────────────────────
"""

print(PATCH_B_INSTRUCTIONS)
