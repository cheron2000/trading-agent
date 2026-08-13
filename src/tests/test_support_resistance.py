from data.features.support_resistance import SupportResistanceCalculator


def test_insufficient_data():
    calc = SupportResistanceCalculator(swing_window=5)
    prices = [100.0, 101.0, 102.0]  # Less than 2 * 5 + 1
    result = calc.calculate("TEST", prices, 101.0)

    assert result["supports"] == []
    assert result["resistances"] == []
    assert result["nearest_support"] is None
    assert result["nearest_resistance"] is None
    assert result["support_distance_pct"] is None
    assert result["resistance_distance_pct"] is None


def test_known_swing_points():
    calc = SupportResistanceCalculator(swing_window=5)
    # Clear pattern: valley at 95, peak at 110, valley at 97, peak at 108
    prices = (
        [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100]  # swing low at 95
        + [101, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100]  # swing high at 110
        + [
            99,
            98.5,
            98,
            97.5,
            97.1,
            97.0,
            97.1,
            97.5,
            98,
            98.5,
            99,
            100,
            101,
            102,
        ]  # swing low at 97
        + [
            103,
            105,
            106,
            107,
            107.5,
            108.0,
            107.5,
            107,
            106,
            105,
            104,
            103,
        ]  # swing high at 108
    )
    current_price = 103.0

    result = calc.calculate("PATTERN", prices, current_price)

    # Due to clustering, it might be exactly 97.0 and 108.0 or slightly averaged
    # depending on how exact the peaks were. Here they are exact.
    assert result["nearest_support"] == 97.0
    assert result["nearest_resistance"] == 108.0


def test_distance_calculation():
    calc = SupportResistanceCalculator(swing_window=5)
    prices = (
        [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100]
        + [101, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100]
        + [99, 98.5, 98, 97.5, 97.1, 97.0, 97.1, 97.5, 98, 98.5, 99, 100, 101, 102]
        + [103, 105, 106, 107, 107.5, 108.0, 107.5, 107, 106, 105, 104, 103]
    )
    current_price = 103.0

    result = calc.calculate("DIST", prices, current_price)

    assert result["support_distance_pct"] < 0
    assert result["resistance_distance_pct"] > 0

    expected_supp_dist = ((97.0 - 103.0) / 103.0) * 100
    expected_res_dist = ((108.0 - 103.0) / 103.0) * 100

    assert abs(result["support_distance_pct"] - expected_supp_dist) < 1e-5
    assert abs(result["resistance_distance_pct"] - expected_res_dist) < 1e-5


def test_caching_returns_same_result():
    calc = SupportResistanceCalculator(swing_window=5, cache_ttl_seconds=10.0)
    prices = (
        [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100]
        + [101, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100]
        + [99, 98, 97, 97, 97, 98, 99, 100, 101, 102]
        + [103, 105, 106, 108, 107, 106, 105, 104, 103]
    )
    current_price = 103.0

    result1 = calc.calculate("CACHE", prices, current_price)

    # Modify prices radically, but use same symbol
    modified_prices = [p + 50 for p in prices]
    result2 = calc.calculate("CACHE", modified_prices, current_price + 50)

    # Since TTL is active, it should return the first result
    assert result1 == result2
