"""Quick Finnhub key test."""
import sys
sys.path.insert(0, "src")
from data.providers.finnhub_news_provider import FinnhubNewsProvider
from load_keys import load_finnhub_key

key = load_finnhub_key()
print(f"Finnhub key loaded: {key[:8]}...{key[-4:] if key else 'NONE'}")

n = FinnhubNewsProvider(api_key=key, max_articles=5)

for sym in ["AAPL", "MSFT"]:
    print(f"\n{'='*50}")
    articles = n.fetch_sentiment(sym)
    print(f"{sym}: {len(articles)} article(s)")
    for a in articles:
        lbl = a.get("sentiment_label", "?")
        scr = a.get("sentiment_score", 0.0)
        ttl = a.get("title", "")[:75]
        print(f"  [{lbl} {scr:+.2f}] {ttl}")
    print()
    print(n.format_for_prompt(sym))
