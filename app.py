from flask import Flask, jsonify, request
import requests
from datetime import datetime
from zoneinfo import ZoneInfo  # native timezone support (Python 3.9+)

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
                "exchange": result.get("primary_exchange", exchange),
            }
        url = data.get("next_url")
        params = {"apiKey": API_KEY}
    print(f"[DEBUG] Loaded {len(tickers)} tickers for {exchange}")
    return tickers


def get_market_snapshot():
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    resp = requests.get(url, params=params)
    data = resp.json()
    tickers = data.get("tickers", [])
    print(f"[DEBUG] Snapshot contains {len(tickers)} tickers")
    return tickers


def calculate_change_pct(snap):
    price_now = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
    if not price_now:
        return None

    prev = snap.get("prevDay", {})
    today = snap.get("day", {})

    prev_close = prev.get("c")
    today_open = today.get("o")

    # CET tijd ophalen
    now_cet = datetime.now(ZoneInfo("Europe/Paris"))
    total_minutes = now_cet.hour * 60 + now_cet.minute

    if total_minutes < (21 * 60):  # tot 21:00 CET
        base_price = prev_close
        logic = "using prevDay close"
    else:  # na 21:00 CET
        base_price = today_open or prev_close
        logic = "using today open"

    if not base_price or base_price == 0:
        return None

    change = (price_now - base_price) / base_price * 100
    print(f"[DEBUG] {snap.get('ticker')} {logic}: price_now={price_now}, base={base_price}, change={change:.2f}%")
    return change


def get_top_losers(limit=10):
    nyse = get_common_stocks("XNYS")
    nasdaq = get_common_stocks("XNAS")
    common_tickers = nyse.union(nasdaq)
    snapshot_data = get_market_snapshot()
    losers = []

    # Debug counters
    checked = 0
    skipped_price = 0
    skipped_change = 0
    skipped_not_common = 0

    for snap in snapshot_data:
        ticker = snap.get("ticker", "").upper()
        checked += 1
        if ticker not in common_tickers:
            skipped_not_common += 1
            continue

        price = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
        if not price or price < 15:
            skipped_price += 1
            continue

        change_pct = calculate_change_pct(snap)
        if change_pct is None or change_pct >= 0:
            skipped_change += 1
            continue

        meta = ticker_metadata.get(ticker, {})
        losers.append(
            {
                "ticker": ticker,
                "name": meta.get("name", ""),
                "exchange": meta.get("exchange", ""),
                "currentPrice": round(price, 2),
                "changePct": round(change_pct, 2),
                "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
            }
        )

    losers = sorted(losers, key=lambda x: x["changePct"])[:limit]

    print(f"[DEBUG] Total tickers checked: {checked}")
    print(f"[DEBUG] Skipped (not common stock): {skipped_not_common}")
    print(f"[DEBUG] Skipped (price < 15 or missing): {skipped_price}")
    print(f"[DEBUG] Skipped (no negative change): {skipped_change}")
    print(f"[DEBUG] Final losers count: {len(losers)}")

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
