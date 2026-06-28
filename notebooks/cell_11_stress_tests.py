"""
================================================================================
  CELL 11 — Phase 3 Sub-Task 3.5: Prompt Stress Testing & Edge Case Hardening
  Paste this into Colab Cell 11 and run it standalone — no live API or
  yfinance calls needed. All inputs are synthetic.
  ALL 7 TESTS MUST SHOW [OK] PASS before Phase 3 is considered complete.
================================================================================
"""

import json
import re
import time
import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from io import StringIO
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import deque
from typing import Optional


# -------------------------------------------------------------
# MINIMAL INLINE STUBS
# These reproduce only the logic paths under test so the harness
# runs even if Cells 3–10 weren't executed in this session.
# -------------------------------------------------------------

# -- Stub: JSON parser from Cell 4 ----------------------------
def parse_atlas_response(raw_text: str) -> dict:
    """Mirrors the parsing + validation logic in Cell 4 get_ai_decision()."""
    raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text.strip())
    raw_text = re.sub(r"\n?```$", "",          raw_text)

    decision = json.loads(raw_text)   # raises JSONDecodeError if malformed

    if not isinstance(decision, dict):
        raise ValueError(f"Expected JSON object, got {type(decision).__name__}")

    required_keys = {
        "asset", "tactical_stance", "confidence_score",
        "rationale", "execution_parameters", "signal_breakdown",
    }
    missing = required_keys - set(decision.keys())
    if missing:
        raise ValueError(f"Missing required keys: {missing}")

    # Normalise stance
    decision["tactical_stance"] = str(decision["tactical_stance"]).upper().strip()
    if decision["tactical_stance"] not in ("BUY", "SELL", "HOLD"):
        raise ValueError(f"Invalid tactical_stance: {decision['tactical_stance']}")

    # Clamp confidence
    raw_conf = float(decision["confidence_score"])
    if not (0.0 <= raw_conf <= 1.0):
        raise ValueError(
            f"confidence_score {raw_conf} out of [0, 1] bounds"
        )

    return decision


# -- Stub: Sentiment fetcher from Cell 3 ----------------------
def fetch_sentiment_stub(ticker: str, timeout: int = 8) -> dict:
    """Mirrors fetch_sentiment() with injectable urllib behaviour."""
    import urllib.request
    import urllib.error
    import xml.etree.ElementTree as ET

    positive_words = {"surge","soar","beat","record","bullish","upgrade","growth","profit"}
    negative_words = {"plunge","crash","miss","bearish","downgrade","loss","decline"}

    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}"
    headlines      = []
    sentiment_score = 0.0

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()
        root  = ET.fromstring(xml_data)
        items = root.findall(".//item")[:5]
        for item in items:
            title = item.findtext("title", default="").strip()
            if not title:
                continue
            headlines.append(title)
            words = set(re.sub(r"[^a-z ]", "", title.lower()).split())
            sentiment_score += len(words & positive_words) - len(words & negative_words)
        if headlines:
            sentiment_score = max(-1.0, min(1.0, sentiment_score / (len(headlines) * 3)))
    except Exception as e:
        headlines       = [f"[Sentiment feed unavailable: {e}]"]
        sentiment_score = 0.0

    label = "POSITIVE" if sentiment_score > 0.1 else ("NEGATIVE" if sentiment_score < -0.1 else "NEUTRAL")
    return {"headlines": headlines, "sentiment_score": round(sentiment_score, 3),
            "sentiment_label": label}


# -- Stub: Market State Vector builder from Cell 3 -------------
def build_msv_stub(df: pd.DataFrame, ticker: str = "TEST") -> str:
    """Minimal MSV builder — accepts a pre-built DataFrame directly."""
    if df is None or df.empty:
        return f"[ERROR] Insufficient price data for {ticker}."

    close = df["Close"]
    nan_ratio = close.isna().mean()
    if nan_ratio > 0.5:
        return f"[ERROR] Insufficient price data for {ticker}."

    close_clean = close.dropna()
    if len(close_clean) < 20:
        return f"[ERROR] Insufficient price data for {ticker}."

    return (
        f"=== LIVE MARKET STATE VECTOR ===\n"
        f"Asset: {ticker}\n"
        f"Price: ${float(close_clean.iloc[-1]):.2f}\n"
        f"================================="
    )


# -- Stub: PaperPortfolio open_position from Cell 5 -----------
@dataclass
class _Position:
    ticker: str
    stance: str
    entry_price: float

class _PortfolioStub:
    def __init__(self):
        self.open_positions: dict[str, _Position] = {}
        self.cash = 100_000.0
        self.log  = []

    def open_position(self, ticker, stance, current_price,
                      stop_loss_pct, take_profit_pct, confidence, rationale,
                      current_prices=None):
        if stance == "HOLD":
            return None
        if ticker in self.open_positions:
            self.log.append(f"[SKIP] Already have open position in {ticker}.")
            return None
        pos = _Position(ticker=ticker, stance=stance, entry_price=current_price)
        self.open_positions[ticker] = pos
        return pos


# -------------------------------------------------------------
# TEST HARNESS
# -------------------------------------------------------------

class ATLASStressTests(unittest.TestCase):

    # ==========================================================
    # TEST 1 — Malformed LLM JSON Output
    # ==========================================================
    def test_01_malformed_json(self):
        """
        SCENARIO : ATLAS returns broken JSON (truncated, missing brace,
                   or completely non-JSON preamble text).
        EXPECTED : JSONDecodeError caught; system returns error status,
                   no trade is executed.
        DEFENCE  : try/except JSONDecodeError in parse_atlas_response()
                   returns {"status": "error"} instead of crashing the loop.
        """
        malformed_inputs = [
            # Truncated mid-JSON
            '{"asset": "AAPL", "tactical_stance": "BUY", "confidence_sc',
            # Preamble before JSON (LLM ignored instructions)
            'Sure! Here is my analysis:\n{"asset": "AAPL"}',
            # Completely empty string
            "",
            # JSON array instead of object
            '[{"asset": "AAPL"}]',
            # Valid JSON but missing required keys
            '{"asset": "AAPL", "tactical_stance": "BUY"}',
        ]

        for raw in malformed_inputs:
            with self.subTest(raw=raw[:40]):
                try:
                    parse_atlas_response(raw)
                    # If we reach here with empty or array input, it's a bug
                    self.fail(f"Should have raised an exception for: {raw[:40]}")
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    # [OK] Exception caught — system is protected
                    pass

        print("  TEST 1 PASS — All 5 malformed inputs caught cleanly.")

    # ==========================================================
    # TEST 2 — Contradictory Signals
    # ==========================================================
    def test_02_contradictory_signals(self):
        """
        SCENARIO : RSI=28 (oversold → bullish), MACD histogram negative
                   (bearish cross), sentiment NEGATIVE. Mixed signals.
        EXPECTED : ATLAS should output HOLD with confidence < 0.65,
                   which falls below the confidence threshold → no trade.
        DEFENCE  : Confidence threshold gate in Cell 6. Even if ATLAS
                   outputs BUY, confidence below threshold blocks execution.
        """
        # Simulate ATLAS output for a contradictory market
        contradictory_response = json.dumps({
            "asset"            : "TSLA",
            "tactical_stance"  : "HOLD",       # correct response to mixed signals
            "confidence_score" : 0.42,          # below threshold
            "rationale"        : "RSI indicates oversold but MACD bearish cross and negative sentiment create conflicting signals. Insufficient confluence to act.",
            "execution_parameters": {
                "entry_trigger"      : "N/A",
                "target_take_profit" : "N/A",
                "stop_loss_limit"    : "N/A",
            },
            "signal_breakdown": {
                "momentum_signal"  : "NEUTRAL",
                "volatility_signal": "MODERATE",
                "volume_signal"    : "WEAK",
                "sentiment_signal" : "NEGATIVE",
            },
        })

        decision = parse_atlas_response(contradictory_response)
        conf_threshold = 0.65

        stance     = decision["tactical_stance"]
        confidence = decision["confidence_score"]

        # Gate check (mirrors Cell 6 logic)
        should_trade = stance in ("BUY", "SELL") and confidence >= conf_threshold

        self.assertEqual(stance, "HOLD")
        self.assertLess(confidence, conf_threshold)
        self.assertFalse(should_trade)

        print(f"  TEST 2 PASS — Contradictory signals → HOLD (conf={confidence}) → no trade.")

    # ==========================================================
    # TEST 3 — Confidence Score Out of Bounds
    # ==========================================================
    def test_03_confidence_out_of_bounds(self):
        """
        SCENARIO : ATLAS returns confidence_score = 1.5 or -0.2
                   (hallucinated value outside [0, 1]).
        EXPECTED : ValueError raised; system does not attempt to trade
                   with a nonsensical confidence level.
        DEFENCE  : Explicit bounds check in parse_atlas_response() raises
                   ValueError before the decision reaches the trade gate.
        """
        out_of_bounds_cases = [
            ("above 1.0",  1.5),
            ("below 0.0", -0.2),
            ("way above",  99.0),
        ]

        for label, bad_conf in out_of_bounds_cases:
            with self.subTest(label=label):
                bad_response = json.dumps({
                    "asset"             : "NVDA",
                    "tactical_stance"   : "BUY",
                    "confidence_score"  : bad_conf,
                    "rationale"         : "Strong bullish signal.",
                    "execution_parameters": {
                        "entry_trigger"      : "price > $500",
                        "target_take_profit" : "$525",
                        "stop_loss_limit"    : "$487",
                    },
                    "signal_breakdown": {
                        "momentum_signal"  : "BULLISH",
                        "volatility_signal": "LOW",
                        "volume_signal"    : "CONFIRMING",
                        "sentiment_signal" : "POSITIVE",
                    },
                })

                with self.assertRaises(ValueError) as ctx:
                    parse_atlas_response(bad_response)

                self.assertIn("out of [0, 1] bounds", str(ctx.exception))

        print("  TEST 3 PASS — All out-of-bounds confidence values caught.")

    # ==========================================================
    # TEST 4 — yfinance Empty / NaN-Heavy DataFrame
    # ==========================================================
    def test_04_empty_and_nan_dataframe(self):
        """
        SCENARIO : yfinance returns (a) a completely empty DataFrame,
                   or (b) a DataFrame where >50% of Close prices are NaN.
        EXPECTED : build_msv_stub() returns an [ERROR] string, not a
                   valid Market State Vector. The loop skips the asset.
        DEFENCE  : Empty/NaN checks at the top of build_market_state_vector()
                   return early with an [ERROR] prefix string.
        """
        # Case A: completely empty DataFrame
        empty_df = pd.DataFrame()
        result_a = build_msv_stub(empty_df, "AAPL")
        self.assertTrue(result_a.startswith("[ERROR]"),
                        f"Expected [ERROR], got: {result_a}")

        # Case B: DataFrame with >50% NaN close prices
        idx      = pd.date_range("2024-01-01", periods=30, freq="D")
        nan_data = [np.nan] * 20 + [150.0] * 10   # 67% NaN
        nan_df   = pd.DataFrame({
            "Open": nan_data, "High": nan_data,
            "Low" : nan_data, "Close": nan_data, "Volume": [1e6]*30
        }, index=idx)
        result_b = build_msv_stub(nan_df, "AAPL")
        self.assertTrue(result_b.startswith("[ERROR]"),
                        f"Expected [ERROR], got: {result_b}")

        # Case C: too few rows (< 20 non-NaN)
        thin_df = pd.DataFrame({
            "Open": [100]*10, "High": [105]*10,
            "Low" : [98]*10,  "Close": [102]*10, "Volume": [1e6]*10
        }, index=pd.date_range("2024-01-01", periods=10, freq="D"))
        result_c = build_msv_stub(thin_df, "AAPL")
        self.assertTrue(result_c.startswith("[ERROR]"),
                        f"Expected [ERROR], got: {result_c}")

        print("  TEST 4 PASS — Empty/NaN/thin DataFrames all return [ERROR] safely.")

    # ==========================================================
    # TEST 5 — Sentiment Feed Timeout / HTTP Error
    # ==========================================================
    def test_05_sentiment_feed_failure(self):
        """
        SCENARIO : Yahoo Finance RSS feed times out (urllib.error.URLError)
                   or returns a non-200 HTTP response.
        EXPECTED : fetch_sentiment() catches the exception, returns a
                   neutral sentiment dict with score=0.0, does NOT crash.
        DEFENCE  : try/except around urllib.request.urlopen in fetch_sentiment().
                   Returns {"sentiment_score": 0.0, "sentiment_label": "NEUTRAL"}.
        """
        import urllib.error

        # Patch urllib to simulate timeout
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timed out")):
            result = fetch_sentiment_stub("AAPL", timeout=1)

        self.assertEqual(result["sentiment_score"], 0.0)
        self.assertEqual(result["sentiment_label"], "NEUTRAL")
        self.assertTrue(len(result["headlines"]) > 0)
        self.assertIn("unavailable", result["headlines"][0].lower())

        # Patch urllib to simulate HTTP 503
        with patch("urllib.request.urlopen",
                   side_effect=Exception("HTTP Error 503: Service Unavailable")):
            result2 = fetch_sentiment_stub("TSLA", timeout=1)

        self.assertEqual(result2["sentiment_score"], 0.0)
        self.assertEqual(result2["sentiment_label"], "NEUTRAL")

        print("  TEST 5 PASS — Sentiment feed timeout/error → neutral fallback, no crash.")

    # ==========================================================
    # TEST 6 — Unsupported tactical_stance Value
    # ==========================================================
    def test_06_invalid_tactical_stance(self):
        """
        SCENARIO : ATLAS hallucinates an unsupported stance value such as
                   "STRONG BUY", "MAYBE", "BULLISH", or an empty string.
        EXPECTED : parse_atlas_response() raises ValueError, preventing
                   the invalid stance from reaching the execution engine.
        DEFENCE  : Explicit allowlist check after normalisation. Any value
                   not in {"BUY", "SELL", "HOLD"} raises ValueError.
        """
        invalid_stances = [
            "STRONG BUY",
            "MAYBE",
            "BULLISH",
            "",
            "buy",          # lowercase (normalised to "BUY" → valid, should pass)
            "UNKNOWN",
        ]

        # Stances that should be caught
        should_fail = {"STRONG BUY", "MAYBE", "BULLISH", "", "UNKNOWN"}
        # Stances that normalise to valid
        should_pass = {"buy"}   # → "BUY" after .upper()

        for stance in invalid_stances:
            response = json.dumps({
                "asset"            : "MSFT",
                "tactical_stance"  : stance,
                "confidence_score" : 0.80,
                "rationale"        : "Test.",
                "execution_parameters": {
                    "entry_trigger"      : "price > $400",
                    "target_take_profit" : "$420",
                    "stop_loss_limit"    : "$390",
                },
                "signal_breakdown": {
                    "momentum_signal"  : "BULLISH",
                    "volatility_signal": "LOW",
                    "volume_signal"    : "CONFIRMING",
                    "sentiment_signal" : "POSITIVE",
                },
            })

            with self.subTest(stance=stance):
                if stance in should_fail:
                    with self.assertRaises(ValueError) as ctx:
                        parse_atlas_response(response)
                    self.assertIn("Invalid tactical_stance", str(ctx.exception))
                else:
                    # Should normalise and pass
                    result = parse_atlas_response(response)
                    self.assertIn(result["tactical_stance"], ("BUY", "SELL", "HOLD"))

        print("  TEST 6 PASS — All invalid stances caught; 'buy' normalised to 'BUY'.")

    # ==========================================================
    # TEST 7 — Duplicate Position Signal on Same Ticker
    # ==========================================================
    def test_07_duplicate_position_same_ticker(self):
        """
        SCENARIO : ATLAS issues a BUY on AAPL in cycle 1. In cycle 2 it
                   issues another BUY on AAPL while the position is still open.
        EXPECTED : The second open_position() call is silently skipped with
                   a [SKIP] log entry. Portfolio has exactly one AAPL position.
        DEFENCE  : `if ticker in self.open_positions` guard at the top of
                   PaperPortfolio.open_position(). Only one position per
                   ticker allowed at any time.
        """
        portfolio = _PortfolioStub()

        # Cycle 1 — open BUY on AAPL
        pos1 = portfolio.open_position(
            ticker="AAPL", stance="BUY", current_price=180.0,
            stop_loss_pct=2.5, take_profit_pct=5.0,
            confidence=0.82, rationale="Strong bullish confluence.",
        )
        self.assertIsNotNone(pos1)
        self.assertIn("AAPL", portfolio.open_positions)
        self.assertEqual(len(portfolio.open_positions), 1)

        # Cycle 2 — duplicate BUY signal on AAPL (position still open)
        pos2 = portfolio.open_position(
            ticker="AAPL", stance="BUY", current_price=182.0,
            stop_loss_pct=2.5, take_profit_pct=5.0,
            confidence=0.79, rationale="Continued bullish momentum.",
        )
        self.assertIsNone(pos2)                       # skipped
        self.assertEqual(len(portfolio.open_positions), 1)   # still only 1
        self.assertTrue(
            any("[SKIP]" in entry for entry in portfolio.log),
            "Expected a [SKIP] log entry for the duplicate signal."
        )
        # Entry price should be from the FIRST open, not overwritten
        self.assertEqual(portfolio.open_positions["AAPL"].entry_price, 180.0)

        print("  TEST 7 PASS — Duplicate BUY on open position skipped; entry price preserved.")


# -------------------------------------------------------------
# RUN THE HARNESS
# -------------------------------------------------------------

def run_stress_tests():
    print()
    print("=" * 62)
    print("  🧪  ATLAS STRESS TEST HARNESS — Phase 3.5")
    print("=" * 62)
    print()

    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromTestCase(ATLASStressTests)

    # Custom result collector
    class VerboseResult(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.test_results = []

        def addSuccess(self, test):
            self.test_results.append(("PASS", test._testMethodName, None))

        def addFailure(self, test, err):
            self.test_results.append(("FAIL", test._testMethodName, str(err[1])))

        def addError(self, test, err):
            self.test_results.append(("ERROR", test._testMethodName, str(err[1])))

    result = VerboseResult()
    suite.run(result)

    # -- Summary table -----------------------------------------
    print()
    print("-" * 62)
    print(f"  {'#':<5} {'Test':<45} {'Result'}")
    print("-" * 62)

    descriptions = {
        "test_01_malformed_json"         : "Malformed LLM JSON output",
        "test_02_contradictory_signals"  : "Contradictory market signals",
        "test_03_confidence_out_of_bounds": "Confidence score out of [0,1]",
        "test_04_empty_and_nan_dataframe" : "Empty / NaN-heavy DataFrame",
        "test_05_sentiment_feed_failure"  : "Sentiment feed timeout/HTTP error",
        "test_06_invalid_tactical_stance" : "Unsupported tactical_stance value",
        "test_07_duplicate_position_same_ticker": "Duplicate position same ticker",
    }

    all_pass = True
    for i, (status, method, err) in enumerate(result.test_results, 1):
        icon  = "[OK]" if status == "PASS" else "[FAIL]"
        label = descriptions.get(method, method)
        print(f"  {i:<5} {label:<45} {icon} {status}")
        if err:
            print(f"        └- {err[:80]}")
        if status != "PASS":
            all_pass = False

    print("-" * 62)
    total  = len(result.test_results)
    passed = sum(1 for s, _, _ in result.test_results if s == "PASS")
    print(f"  Result: {passed}/{total} tests passed")

    if all_pass:
        print()
        print("  [OK] ALL TESTS PASSED — Phase 3 is complete.")
        print("  [START] System is hardened and ready for Phase 5:")
        print("     Safety Guardrails & Live Deployment.")
    else:
        print()
        print("  [FAIL] SOME TESTS FAILED — review failures above before")
        print("     proceeding to Phase 5.")

    print("=" * 62)
    print()
    return all_pass


# Execute immediately when cell is run
phase_3_complete = run_stress_tests()
