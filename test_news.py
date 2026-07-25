"""
test_news.py — Quick test of the news sentiment layer.
Tests AVNewsProvider against all keys in keys.env.

Usage:
    python test_news.py
"""
import sys
sys.path.insert(0, "src")

from data.providers.av_news_provider import AVNewsProvider
from load_keys import load_av_keys

keys = load_av_keys()
print(f"\nTesting news sentiment with {len(keys)} key(s)...\n")

news = AVNewsProvider(api_keys=keys, max_articles=3, cache_ttl=0)  # ttl=0 forces fresh fetch

for symbol in ["AAPL", "MSFT"]:
    print(f"{'='*50}")
    print(f"Symbol: {symbol}")
    try:
        articles = news.fetch_sentiment(symbol)
        if articles:
            print(f"Found {len(articles)} article(s):")
            for a in articles:
                label = a.get("sentiment_label", "?")
                score = a.get("sentiment_score", 0.0)
                title = a.get("title", "")[:70]
                src   = a.get("source", "")
                print(f"  [{label} {score:+.2f}] {title}")
                print(f"   Source: {src}")
            print()
            print("Prompt format preview:")
            print(news.format_for_prompt(symbol))
        else:
            print("No articles returned (keys may be rate limited)")
    except Exception as e:
        print(f"Error: {e}")
    print()
