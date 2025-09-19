from flask import Flask, jsonify, render_template_string, request
import requests
from datetime import datetime
import pytz

app = Flask("Identify_biggest_stocklosers")
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7"
ticker_metadata = {}

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
            ticker = result.get("ticker")
            if not ticker:
                continue
            ticker = ticker.upper()
            tickers.add(ticker)
            ticker_metadata[ticker] = {
                "name": result.get("name", ""),
                "exchange": result.get("primary_exchange", exchange)
            }
        url = data.get("next_url")
        params = {"apiKey": API_KEY}
    return tickers

def get_market_snapshot():
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    resp = requests.get(url, params=params)
    return resp.json().get("tickers", [])

def determine_time_logic():
    cet = pytz.timezone("CET")
    now_cet = datetime.now(cet)

    hour = now_cet.hour
    minute = now_cet.minute
    total_minutes = hour * 60 + minute

    if total_minutes < (14 * 60 + 30):
        return "overnight"  # Before 14:30 CET
    elif total_minutes < (22 * 60):
        return "intraday"   # Between 14:30 and 22:00 CET
    else:
        return "afterhours"  # After 22:00 CET

def calculate_change_pct(snap, logic):
    price_now = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
    if not price_now:
        return None

    prev_day = snap.get("prevDay", {})
    today = snap.get("day", {})

    if logic == "overnight":
        base_price = prev_day.get("o")  # yesterday's open
    elif logic == "intraday":
        base_price = prev_day.get("c")  # yesterday's close
    elif logic == "afterhours":
        base_price = today.get("o")     # today's open
    else:
        base_price = None

    if not base_price or base_price == 0:
        return None

    return (price_now - base_price) / base_price * 100

def get_top_losers(limit=10):
    logic = determine_time_logic()

    nyse = get_common_stocks("XNYS")
    nasdaq = get_common_stocks("XNAS")
    common_tickers = nyse.union(nasdaq)
    snapshot_data = get_market_snapshot()
    losers = []

    for snap in snapshot_data:
        ticker = snap.get("ticker", "").upper()
        if ticker not in common_tickers:
            continue

        price = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
        if not price or price < 15:
            continue

        change_pct = calculate_change_pct(snap, logic)
        if change_pct is None or change_pct >= 0:
            continue

        meta = ticker_metadata.get(ticker, {})
        losers.append({
            "ticker": ticker,
            "name": meta.get("name", ""),
            "exchange": meta.get("exchange", ""),
            "currentPrice": round(price, 2),
            "changePct": round(change_pct, 2),
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}"
        })

    losers = sorted(losers, key=lambda x: x["changePct"])[:limit]
    return losers

@app.route("/top-losers", methods=["GET"])
def api_top_losers():
    try:
        limit = int(request.args.get("limit", 10))
        return jsonify(get_top_losers(limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
