from flask import Flask, jsonify
import requests

app = Flask(__name__)
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7"

def get_common_stocks(exchange):
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
        params = {"apiKey": API_KEY}
    return tickers

def get_market_snapshot():
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    resp = requests.get(url, params=params)
    return resp.json().get("tickers", [])

@app.route("/top-losers", methods=["GET"])
def get_top_losers():
    try:
        nyse = get_common_stocks("XNYS")
        nasdaq = get_common_stocks("XNAS")
        common_tickers = nyse.union(nasdaq)

        snapshot_data = get_market_snapshot()
        losers = []

        for snap in snapshot_data:
            ticker = snap.get("ticker")
            if ticker not in common_tickers:
                continue

            # Extract price
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

        losers = sorted(losers, key=lambda x: x["changePct"])[:10]
        return jsonify(losers)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)