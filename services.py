import requests
import json
import threading
import time
from datetime import date

# --- Configuration ---
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7"
TRACKED_STOCKS_FILE = "tracked_stocks.json"

# --- In-Memory Cache for Stock Data ---
data_lock = threading.Lock()
COMMON_STOCK_TICKERS = set()
TICKER_METADATA = {}
TOP_LOSERS_CACHE = []
LAST_UPDATED = "Not yet updated"

# --- Persistence Helper Functions ---

def load_tracked_stocks():
    """Loads the list of tracked stocks from the JSON file."""
    try:
        with open(TRACKED_STOCKS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_tracked_stocks(stocks):
    """Saves the list of tracked stocks to the JSON file."""
    with open(TRACKED_STOCKS_FILE, 'w') as f:
        json.dump(stocks, f, indent=4)

# --- Data Fetching and Processing ---

def load_common_stocks():
    """Fetches all common stock tickers from NYSE and NASDAQ once at startup."""
    global COMMON_STOCK_TICKERS, TICKER_METADATA
    print("--- Loading common stock tickers ---")
    for exchange in ["XNYS", "XNAS"]:
        url = "https://api.polygon.io/v3/reference/tickers"
        params = {"apiKey": API_KEY, "type": "CS", "market": "stocks", "exchange": exchange, "active": "true", "limit": 1000}
        try:
            while url:
                resp = requests.get(url, params=params)
                if resp.status_code != 200: break
                data = resp.json()
                for result in data.get("results", []):
                    ticker = result.get("ticker")
                    if ticker and " " not in ticker and "." not in ticker:
                        ticker = ticker.upper()
                        COMMON_STOCK_TICKERS.add(ticker)
                        TICKER_METADATA[ticker] = {"name": result.get("name", "N/A"), "exchange": result.get("primary_exchange", exchange)}
                url = data.get("next_url")
                params = {"apiKey": API_KEY}
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Network error while fetching {exchange}: {e}")
    print(f"--- Loaded {len(COMMON_STOCK_TICKERS)} common stock tickers ---")

def update_top_losers_cache(min_price=15.0):
    """Fetches the latest market data and updates the top losers cache."""
    global TOP_LOSERS_CACHE, LAST_UPDATED
    print("--- Background task: Updating top losers cache... ---")
    snapshot_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    try:
        resp = requests.get(snapshot_url, params=params)
        if resp.status_code != 200: return
        snapshot_data = resp.json().get("tickers", [])
    except requests.exceptions.RequestException: return

    calculated_losers = []
    local_tickers = COMMON_STOCK_TICKERS.copy()
    local_metadata = TICKER_METADATA.copy()

    for snap in snapshot_data:
        ticker = snap.get("ticker", "").upper()
        if ticker not in local_tickers: continue
        previous_close = snap.get("prevDay", {}).get("c")
        if not previous_close or previous_close < min_price: continue
        current_price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c")
        if not current_price: continue
        change_pct = ((current_price - previous_close) / previous_close) * 100
        if change_pct >= 0: continue
        meta = local_metadata.get(ticker, {})
        calculated_losers.append({
            "ticker": ticker, "name": meta.get("name", "N/A"), "exchange": meta.get("exchange", "N/A"),
            "currentPrice": round(current_price, 2), "changePct": round(change_pct, 2),
            "previousClose": round(previous_close, 2), # Store this for accurate tracking start
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
        })
    sorted_losers = sorted(calculated_losers, key=lambda x: x["changePct"])
    with data_lock:
        TOP_LOSERS_CACHE = sorted_losers
        LAST_UPDATED = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"--- Cache updated with {len(sorted_losers)} losers ---")

def get_top_losers_from_cache(limit=10):
    with data_lock:
        return TOP_LOSERS_CACHE[:limit]

def get_last_update_time():
    with data_lock:
        return LAST_UPDATED

def add_stocks_to_tracker(tickers_to_track):
    """Adds selected stocks to the persistent tracking file."""
    tracked_stocks = load_tracked_stocks()
    tracked_tickers = {s['ticker'] for s in tracked_stocks}
    with data_lock:
        full_loser_list = TOP_LOSERS_CACHE[:]
    
    for ticker in tickers_to_track:
        if ticker in tracked_tickers: continue
        stock_data = next((item for item in full_loser_list if item["ticker"] == ticker), None)
        if stock_data:
            tracked_stocks.append({
                "ticker": ticker,
                "name": stock_data.get('name'),
                "start_date": date.today().isoformat(),
                "start_price": stock_data.get('previousClose') # Use stable previous close as starting price
            })
    save_tracked_stocks(tracked_stocks)

def get_evaluation_data():
    """Fetches and calculates all data needed for the evaluation page."""
    tracked_stocks = load_tracked_stocks()
    tracked_stocks_data = []
    
    with data_lock:
        current_losers = TOP_LOSERS_CACHE[:]
    
    tracked_tickers = {s['ticker'] for s in tracked_stocks}
    stocks_to_add = [s for s in current_losers if s['ticker'] not in tracked_tickers][:10]

    if not tracked_stocks:
        return stocks_to_add, []

    # Get a full market snapshot to find current prices for tracked stocks
    snapshot_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    try:
        resp = requests.get(snapshot_url, params=params)
        snapshot_map = {s['ticker']: s for s in resp.json().get("tickers", [])} if resp.status_code == 200 else {}
    except requests.exceptions.RequestException:
        snapshot_map = {}

    for stock in tracked_stocks:
        today = date.today()
        start_date = date.fromisoformat(stock['start_date'])
        days_tracked = max(1, (today - start_date).days) # Avoid division by zero
        
        current_price = stock['start_price'] # Default value
        if stock['ticker'] in snapshot_map:
            snap = snapshot_map[stock['ticker']]
            current_price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c") or current_price

        current_change_pct = ((current_price - stock['start_price']) / stock['start_price']) * 100 if stock['start_price'] != 0 else 0
        avg_daily_change_pct = current_change_pct / days_tracked

        # Fetch historical data for max swing
        max_swing = 0
        # BUG FIX: Only fetch history if there is at least one full day to look at.
        if today > start_date:
            try:
                hist_url = f"https://api.polygon.io/v2/aggs/ticker/{stock['ticker']}/range/1/day/{start_date.isoformat()}/{today.isoformat()}"
                hist_resp = requests.get(hist_url, params={"apiKey": API_KEY})
                if hist_resp.status_code == 200:
                    results = hist_resp.json().get('results', [])
                    # BUG FIX: Ensure results is not empty before finding max/min
                    if results:
                        highs = [r['h'] for r in results]
                        lows = [r['l'] for r in results]
                        max_swing = max(highs) - min(lows)
            except (requests.exceptions.RequestException, ValueError):
                max_swing = 0 # API failed or list was empty

        tracked_stocks_data.append({
            **stock, "current_price": current_price, "current_change_pct": current_change_pct,
            "avg_daily_change_pct": avg_daily_change_pct, "max_swing": max_swing,
        })
    
    return stocks_to_add, tracked_stocks_data
