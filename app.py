from flask import Flask, jsonify, request
import requests

app = Flask("Identify_biggest_stocklosers")

# --- Configuration ---
# API key is hardcoded as requested.
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7" # Replace with your actual key

# --- In-Memory Cache ---
# These are populated once at startup for performance.
COMMON_STOCK_TICKERS = set()
TICKER_METADATA = {}


def load_common_stocks():
    """
    Fetches all common stock tickers from NYSE and NASDAQ once at startup
    and stores them in global variables for fast lookups during requests.
    This avoids slow, repetitive API calls.
    """
    print("🚀 Initializing: Loading common stock tickers from NYSE and NASDAQ...")
    for exchange in ["XNYS", "XNAS"]:
        url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "apiKey": API_KEY, "type": "CS", "market": "stocks",
            "exchange": exchange, "active": "true", "limit": 1000,
        }
        
        while url:
            try:
                resp = requests.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for result in data.get("results", []):
                    ticker = result.get("ticker")
                    if ticker:
                        ticker = ticker.upper()
                        COMMON_STOCK_TICKERS.add(ticker)
                        TICKER_METADATA[ticker] = {
                            "name": result.get("name", "N/A"),
                            "exchange": result.get("primary_exchange", exchange),
                        }
                
                url = data.get("next_url")
                params = {"apiKey": API_KEY}
            
            except requests.exceptions.RequestException as e:
                print(f"Error fetching tickers for {exchange}: {e}")
                url = None

    print(f"✅ Loaded {len(COMMON_STOCK_TICKERS)} common stock tickers.")


def get_market_snapshot():
    """Fetches a snapshot of the entire US stock market."""
    url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        print(f"[DEBUG] Snapshot received with {len(data.get('tickers', []))} tickers.")
        return data.get("tickers", [])
    except requests.exceptions.RequestException as e:
        print(f"API Error fetching market snapshot: {e}")
        return []


def calculate_change_pct(snap):
    """
    FIXED: Calculates the percentage change reliably.
    The daily change is always based on the previous day's closing price.
    This removes the faulty time-based logic which caused the empty results.
    """
    # Use the most recent price available. 'lastTrade' is often more current than 'day'.
    price_now = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c")
    
    # The base price for daily change is ALWAYS the previous day's close.
    prev_close = snap.get("prevDay", {}).get("c")

    if not price_now or not prev_close or prev_close == 0:
        return None # Cannot calculate if data is missing

    change = (price_now - prev_close) / prev_close * 100
    return change


def get_top_losers(limit=10):
    """
    Gets the full market snapshot, filters for common stocks, calculates the
    change for each, and returns the top losers.
    """
    if not COMMON_STOCK_TICKERS:
        return {"error": "Common stock list is not yet loaded. Please wait and try again."}

    snapshot_data = get_market_snapshot()
    losers = []

    for snap in snapshot_data:
        ticker = snap.get("ticker", "").upper()

        # Filter 1: Must be a common stock we identified at startup
        if ticker not in COMMON_STOCK_TICKERS:
            continue

        # Filter 2: Must have a valid price >= $15
        price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c")
        if not price or price < 15:
            continue

        # Filter 3: Must have a negative change (i.e., be a loser)
        change_pct = calculate_change_pct(snap)
        if change_pct is None or change_pct >= 0:
            continue

        # If all filters pass, add it to our list
        meta = TICKER_METADATA.get(ticker, {})
        losers.append({
            "ticker": ticker,
            "name": meta.get("name", "N/A"),
            "exchange": meta.get("exchange", "N/A"),
            "currentPrice": round(price, 2),
            "changePct": round(change_pct, 2),
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
        })

    # Sort the collected losers by the percentage change and apply the limit
    losers = sorted(losers, key=lambda x: x["changePct"])[:limit]
    
    print(f"[DEBUG] Found {len(losers)} top losers matching criteria.")
    return losers


@app.route("/top-losers", methods=["GET"])
def api_top_losers():
    """Flask API endpoint to get the top N losers."""
    try:
        limit = int(request.args.get("limit", 10))
        return jsonify(get_top_losers(limit))
    except Exception as e:
        print(f"An unexpected error occurred in the API route: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == "__main__":
    # Load the essential ticker data ONCE before starting the web server.
    load_common_stocks()
    # Run the Flask app
    app.run(host="0.0.0.0", port=10000)
