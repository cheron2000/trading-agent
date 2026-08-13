# Task 2: Support & Resistance Level Calculator

## Goal
Build a module that identifies the nearest support and resistance price levels
from recent historical price data. These levels are injected into the ATLAS LLM
prompt so the AI knows where major price barriers exist.

---

## File to Create

**Path:** `src/data/features/support_resistance.py`

---

## Class Specification

```python
class SupportResistanceCalculator:
    """
    Identifies key support and resistance levels from a price series
    using swing high/low detection.
    
    A swing high is a price point higher than its N neighbors on both sides.
    A swing low is a price point lower than its N neighbors on both sides.
    
    Returns the 2 nearest support levels (below current price) and
    2 nearest resistance levels (above current price).
    
    Caching:
      - Results are cached per symbol with a 15-minute TTL.
    """
```

### Constructor

```python
def __init__(self, swing_window: int = 5, cache_ttl_seconds: float = 900.0) -> None:
```

- `swing_window`: Number of bars on each side to confirm a swing point (default 5)
- `cache_ttl_seconds`: TTL for cached levels (default 900 = 15 min)
- Internal state:
  - `self._cache: dict[str, tuple[list[float], list[float], float]]` — `{symbol: (supports, resistances, cached_at)}`

### Method: `calculate(symbol: str, prices: list[float], current_price: float) -> dict`

**Returns:** A dictionary with this exact structure:
```python
{
    "supports": [float, ...],      # Up to 2 nearest support levels (descending, closest first)
    "resistances": [float, ...],   # Up to 2 nearest resistance levels (ascending, closest first)
    "nearest_support": float | None,     # Closest support below current price
    "nearest_resistance": float | None,  # Closest resistance above current price
    "support_distance_pct": float | None,  # % distance to nearest support (negative number)
    "resistance_distance_pct": float | None,  # % distance to nearest resistance (positive number)
}
```

**Algorithm:**

1. **Check cache:** If symbol exists in cache and not expired, return cached result.

2. **Find swing highs (resistance candidates):**
   For each index `i` in `range(swing_window, len(prices) - swing_window)`:
   ```python
   left_window = prices[i - swing_window : i]
   right_window = prices[i + 1 : i + 1 + swing_window]
   if prices[i] > max(left_window) and prices[i] > max(right_window):
       swing_highs.append(prices[i])
   ```

3. **Find swing lows (support candidates):**
   Same pattern but check if `prices[i] < min(left_window) and prices[i] < min(right_window)`.

4. **Cluster nearby levels:**
   Merge levels that are within 0.5% of each other (they represent the same zone).
   Keep the average of merged levels.
   
   ```python
   def _cluster_levels(levels: list[float], threshold_pct: float = 0.5) -> list[float]:
       """Merge levels within threshold_pct of each other."""
       if not levels:
           return []
       sorted_levels = sorted(levels)
       clusters = [[sorted_levels[0]]]
       for level in sorted_levels[1:]:
           if (level - clusters[-1][-1]) / clusters[-1][-1] * 100 < threshold_pct:
               clusters[-1].append(level)
           else:
               clusters.append([level])
       return [sum(c) / len(c) for c in clusters]
   ```

5. **Filter and sort:**
   - Supports = all clustered swing lows WHERE level < current_price, sorted descending (closest first)
   - Resistances = all clustered swing highs WHERE level > current_price, sorted ascending (closest first)
   - Take top 2 of each.

6. **Compute distances:**
   ```python
   nearest_support = supports[0] if supports else None
   nearest_resistance = resistances[0] if resistances else None
   support_distance_pct = ((nearest_support - current_price) / current_price * 100) if nearest_support else None
   resistance_distance_pct = ((nearest_resistance - current_price) / current_price * 100) if nearest_resistance else None
   ```

7. **Cache and return.**

**Edge Cases:**
- If `len(prices) < 2 * swing_window + 1`: return empty result `{"supports": [], "resistances": [], "nearest_support": None, "nearest_resistance": None, "support_distance_pct": None, "resistance_distance_pct": None}`
- If no swing highs/lows found: return empty result
- If current_price <= 0: return empty result

---

## Data Source

The price data comes from `provider.fetch_recent(symbol, n=100)` in `run_hour.py`.
Currently `fetch_recent` returns the last `n` ticks. For S/R calculation,
you need MORE data than the current 26-tick window.

**IMPORTANT:** You will need to call `provider.fetch_recent(symbol, n=100)` separately
in the integration step (Task 3) to get enough data for meaningful S/R levels.
The `YFinanceProvider.fetch_recent()` method already supports arbitrary `n` values.

---

## Test File to Create

**Path:** `src/tests/test_support_resistance.py`

Write at least 4 tests:

1. **test_insufficient_data**: Pass fewer than `2 * swing_window + 1` prices. Assert all fields are None/empty.

2. **test_known_swing_points**: Create a price series with clear swing patterns:
   ```python
   # Clear pattern: valley at 95, peak at 110, valley at 97, peak at 108
   prices = (
       [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100]   # swing low at 95
       + [101, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100]  # swing high at 110
       + [99, 98, 97, 97, 97, 98, 99, 100, 101, 102]  # swing low at 97
       + [103, 105, 106, 108, 107, 106, 105, 104, 103]  # swing high at 108
   )
   current_price = 103.0
   ```
   Assert that `nearest_support` is around 97 and `nearest_resistance` is around 108.

3. **test_distance_calculation**: Using the above pattern, verify that `support_distance_pct` is negative and `resistance_distance_pct` is positive.

4. **test_caching_returns_same_result**: Call `calculate()` twice rapidly with same inputs. Verify second call returns identical result (cache hit).

Import path: `from data.features.support_resistance import SupportResistanceCalculator`

---

## Important Constraints

- Use ONLY Python stdlib (no numpy, no pandas, no scipy)
- The module must be fully self-contained — no imports from other project modules
- Keep the class stateless except for the TTL cache
- Logging: use `logging.getLogger(__name__)` sparingly (debug level only)
