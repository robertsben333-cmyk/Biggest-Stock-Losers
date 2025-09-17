from flask import Flask, jsonify
import requests

# Optional: use a custom app name for clarity
app = Flask("Identify_biggest_stocklosers")

# Your hardcoded Polygon.io API key
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7"

def get_common_stocks(exchange):
    """Fetch all active common stocks (type=CS) from a specific exchange (XNYS or XNAS)."""
    url = "https://api.polygon.io/v3/reference/tickers"
    params = {
        "apiKey": API_KEY,
        "type": "CS",
        "market": "stocks",
        "exchange": exchange,
        "active": "true",
        "limit": 1000,
    }
    tickers = set()
    while url:
        resp = requests.get(url, params=params)
        data = resp.json()
        for result in data.get("results", []):
            tickers.add(result["ticker"])
        url = data.get("next_url")
        params = {"apiKey": API_KEY}  # For subsequent pages, only use apiKey
    return tickers

def get_market_snapshot():
    """Fetch the full U.S. market snapshot (non-OTC) from Polygon."""
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    resp = requests.get(url, params=params)
    return resp.json().get("tickers", [])

@app.route("/", methods=["GET"])
def home():
    return "✅ Identify_biggest_stocklosers API is live. Use /top-losers to get the top 10 biggest stock losers."

@app.route("/top-losers", methods=["GET"])
def get_top_losers():
    try:
        # Step 1: Get common stock tickers from NYSE and NASDAQ
        nyse = get_common_stocks("XNYS")
        nasdaq = get_common_stocks("XNAS")
        common_tickers = nyse.union(nasdaq)

        # Step 2: Get full market snapshot
        snapshot_data = get_market_snapshot()
        losers = []

        # Step 3: Filter and compute percentage loss
        for snap in snapshot_data:
            ticker = snap.get("ticker")
            if ticker not in common_tickers:
                continue

            price = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
            if not price or price < 15:
                continue

            change_pct = snap.get("todaysChangePerc")
            if change_pct is None or change_pct >= 0:
                continue

            losers.append({
                "ticker": ticker,
                "currentPrice": round(price, 2),
                "changePct": round(change_pct, 2)
            })

        # Step 4: Sort by biggest loss and return top 10
        losers = sorted(losers, key=lambda x: x["changePct"])[:10]
        return jsonify(losers)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Required port for Render
    app.run(host="0.0.0.0", port=10000)
