from flask import Flask, jsonify, render_template_string, request, redirect, url_for
import requests
import json
import threading
import time
from datetime import datetime, date

# --- Flask App Initialization ---
app = Flask("Identify_biggest_stocklosers")

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
    print("--- Loading all common stock tickers from NYSE and NASDAQ ---")
    for exchange in ["XNYS", "XNAS"]:
        url = "https://api.polygon.io/v3/reference/tickers"
        params = {
            "apiKey": API_KEY, "type": "CS", "market": "stocks",
            "exchange": exchange, "active": "true", "limit": 1000,
        }
        print(f"Fetching tickers for {exchange}...")
        try:
            while url:
                resp = requests.get(url, params=params)
                if resp.status_code != 200: break
                data = resp.json()
                with data_lock:
                    for result in data.get("results", []):
                        ticker = result.get("ticker")
                        if ticker and " " not in ticker and "." not in ticker:
                            ticker = ticker.upper()
                            COMMON_STOCK_TICKERS.add(ticker)
                            TICKER_METADATA[ticker] = {
                                "name": result.get("name", "N/A"),
                                "exchange": result.get("primary_exchange", exchange),
                            }
                url = data.get("next_url")
                params = {"apiKey": API_KEY}
        except requests.exceptions.RequestException as e:
            print(f"  [FATAL ERROR] A network error occurred while fetching {exchange}: {e}")
    print(f"--- ✅ Complete: Loaded {len(COMMON_STOCK_TICKERS)} unique common stock tickers. ---\n")


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
    with data_lock:
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
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
        })
    sorted_losers = sorted(calculated_losers, key=lambda x: x["changePct"])
    with data_lock:
        TOP_LOSERS_CACHE = sorted_losers
        LAST_UPDATED = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"--- ✅ Background task complete: Found {len(sorted_losers)} losers. Cache updated. ---")

# --- HTML Templates ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Top Stock Losers</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body { font-family: 'Inter', sans-serif; } .change-negative { color: #ef4444; }</style>
</head>
<body class="bg-gray-100 text-gray-800">
    <div class="container mx-auto px-4 py-8">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-900">Top Stock Losers</h1>
            <p class="text-gray-600 mt-2">The biggest stock decliners on NYSE & NASDAQ (Price >= $15)</p>
            <p class="text-sm text-gray-500 mt-1">Last updated: {{ last_updated }}</p>
        </header>

        <form action="/" method="GET" class="flex justify-center items-center flex-wrap gap-4 mb-8">
            <div class="flex items-center space-x-2">
                <label for="limit" class="text-sm font-medium text-gray-700">Show:</label>
                <input type="number" name="limit" id="limit" value="{{ limit }}" min="1" max="100" class="w-20 px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit" class="px-5 py-2 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400">Refresh</button>
            <a href="/api/top-losers?limit={{ limit }}" target="_blank" class="px-5 py-2 bg-gray-700 text-white font-semibold rounded-lg shadow-md hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-500">JSON</a>
            <a href="{{ url_for('evaluation') }}" class="px-5 py-2 bg-green-600 text-white font-semibold rounded-lg shadow-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500">Evaluation Page</a>
        </form>
        
        <div class="bg-white rounded-lg shadow-lg overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-50 border-b-2 border-gray-200">
                        <tr>
                            <th class="p-4 text-left text-sm font-semibold text-gray-600 uppercase tracking-wider">Ticker</th>
                            <th class="p-4 text-left text-sm font-semibold text-gray-600 uppercase tracking-wider">Company Name</th>
                            <th class="p-4 text-left text-sm font-semibold text-gray-600 uppercase tracking-wider">Exchange</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase tracking-wider">Price</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase tracking-wider">% Change</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200">
                        {% for stock in stocks %}
                        <tr>
                            <td class="p-4 whitespace-nowrap"><a href="{{ stock.yahooLink }}" target="_blank" class="font-bold text-blue-600 hover:underline">{{ stock.ticker }}</a></td>
                            <td class="p-4 text-gray-700">{{ stock.name }}</td>
                            <td class="p-4 text-gray-500">{{ stock.exchange }}</td>
                            <td class="p-4 text-right font-medium">${{ "%.2f"|format(stock.currentPrice) }}</td>
                            <td class="p-4 text-right font-bold change-negative">{{ "%.2f"|format(stock.changePct) }}%</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="5" class="p-8 text-center text-gray-500">No significant stock losers found.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        <footer class="text-center mt-8 text-sm text-gray-500">
            <p>Data provided by <a href="https://polygon.io/" target="_blank" class="text-blue-600 hover:underline">Polygon.io</a>. 15-minute delay.</p>
        </footer>
    </div>
</body>
</html>
"""

EVALUATION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stock Evaluation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        .change-negative { color: #ef4444; }
        .change-positive { color: #22c55e; }
    </style>
</head>
<body class="bg-gray-100 text-gray-800">
    <div class="container mx-auto px-4 py-8">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-900">Stock Evaluation</h1>
            <p class="text-gray-600 mt-2">Track and evaluate the performance of selected stocks over time.</p>
            <a href="{{ url_for('home') }}" class="mt-4 inline-block px-5 py-2 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700">Back to Home</a>
        </header>

        <!-- Section to Add New Stocks -->
        <div class="bg-white rounded-lg shadow-lg overflow-hidden mb-12">
            <h2 class="text-2xl font-bold text-gray-800 p-6 border-b">Add Stocks to Track</h2>
            <p class="text-gray-600 px-6 pb-4">Select from today's top 10 losers to add to your evaluation list.</p>
            <form action="{{ url_for('evaluation') }}" method="POST">
                <div class="p-6">
                    {% if stocks_to_add %}
                        <div class="space-y-4">
                        {% for stock in stocks_to_add %}
                            <label class="flex items-center p-3 rounded-lg hover:bg-gray-50 transition-colors">
                                <input type="checkbox" name="track_ticker" value="{{ stock.ticker }}" class="h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                                <span class="ml-4 font-bold text-blue-600">{{ stock.ticker }}</span>
                                <span class="ml-4 text-gray-700 flex-grow">{{ stock.name }}</span>
                                <span class="ml-4 font-medium">${{ "%.2f"|format(stock.currentPrice) }}</span>
                                <span class="ml-4 font-bold change-negative">{{ "%.2f"|format(stock.changePct) }}%</span>
                            </label>
                        {% endfor %}
                        </div>
                        <button type="submit" class="mt-6 w-full px-6 py-3 bg-green-600 text-white font-semibold rounded-lg shadow-md hover:bg-green-700">Track Selected Stocks</button>
                    {% else %}
                        <p class="text-center text-gray-500">No new stock losers to add, or all are already being tracked.</p>
                    {% endif %}
                </div>
            </form>
        </div>

        <!-- Section for Tracked Stocks -->
        <div class="bg-white rounded-lg shadow-lg overflow-hidden">
            <h2 class="text-2xl font-bold text-gray-800 p-6 border-b">Tracked Stocks Performance</h2>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-50 border-b-2 border-gray-200">
                        <tr>
                            <th class="p-4 text-left text-sm font-semibold text-gray-600 uppercase">Ticker</th>
                            <th class="p-4 text-left text-sm font-semibold text-gray-600 uppercase">Start Date</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase">Start Price</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase">Current Price</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase">Current % Change</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase">Avg. Daily % Change</th>
                            <th class="p-4 text-right text-sm font-semibold text-gray-600 uppercase">Max Price Swing</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200">
                        {% for stock in tracked_stocks_data %}
                        <tr class="{% cycle 'bg-white', 'bg-gray-50' %}">
                            <td class="p-4 whitespace-nowrap"><a href="https://finance.yahoo.com/quote/{{ stock.ticker }}" target="_blank" class="font-bold text-blue-600 hover:underline">{{ stock.ticker }}</a></td>
                            <td class="p-4 text-gray-500">{{ stock.start_date }}</td>
                            <td class="p-4 text-right font-medium">${{ "%.2f"|format(stock.start_price) }}</td>
                            <td class="p-4 text-right font-medium">${{ "%.2f"|format(stock.current_price) }}</td>
                            <td class="p-4 text-right font-bold {% if stock.current_change_pct < 0 %}change-negative{% else %}change-positive{% endif %}">{{ "%.2f"|format(stock.current_change_pct) }}%</td>
                            <td class="p-4 text-right font-bold {% if stock.avg_daily_change_pct < 0 %}change-negative{% else %}change-positive{% endif %}">{{ "%.2f"|format(stock.avg_daily_change_pct) }}%</td>
                            <td class="p-4 text-right font-medium">${{ "%.2f"|format(stock.max_swing) }}</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="7" class="p-8 text-center text-gray-500">You are not tracking any stocks yet.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""

# --- Flask Routes ---

@app.route("/")
def home():
    """Renders the main homepage."""
    threading.Thread(target=update_top_losers_cache).start()
    try: limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError): limit = 10
    with data_lock:
        stocks_to_display = TOP_LOSERS_CACHE[:limit]
        last_update_time = LAST_UPDATED
    return render_template_string(HTML_TEMPLATE, stocks=stocks_to_display, last_updated=last_update_time, limit=limit)

@app.route("/evaluation", methods=['GET', 'POST'])
def evaluation():
    """Renders the evaluation page and handles adding new stocks."""
    if request.method == 'POST':
        tickers_to_track = request.form.getlist('track_ticker')
        if tickers_to_track:
            tracked_stocks = load_tracked_stocks()
            tracked_tickers = {s['ticker'] for s in tracked_stocks}
            
            # Find the data for the newly selected tickers
            with data_lock:
                # We need the full loser list to find the start price
                full_loser_list = TOP_LOSERS_CACHE 
            
            for ticker in tickers_to_track:
                if ticker in tracked_tickers: continue
                
                stock_data = next((item for item in full_loser_list if item["ticker"] == ticker), None)
                if stock_data:
                    # The "start price" is the closing price of the previous day
                    # We need to get this from the snapshot, not the loser list
                    # A quick API call is needed here if not in cache, but let's assume it is for simplicity
                    
                    tracked_stocks.append({
                        "ticker": ticker,
                        "name": stock_data.get('name'),
                        "start_date": date.today().isoformat(),
                        "start_price": stock_data.get('currentPrice') # A simplification, ideally fetch prev close
                    })
            save_tracked_stocks(tracked_stocks)
        return redirect(url_for('evaluation'))

    # Logic for GET request
    tracked_stocks = load_tracked_stocks()
    tracked_stocks_data = []
    
    with data_lock:
        current_losers = TOP_LOSERS_CACHE
    
    # Prepare list of stocks that can be added (top 10 not already tracked)
    tracked_tickers = {s['ticker'] for s in tracked_stocks}
    stocks_to_add = [s for s in current_losers if s['ticker'] not in tracked_tickers][:10]

    if tracked_stocks:
        # Get a full market snapshot to find current prices for tracked stocks
        snapshot_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
        params = {"apiKey": API_KEY, "include_otc": "false"}
        try:
            resp = requests.get(snapshot_url, params=params)
            snapshot_data = resp.json().get("tickers", [])
            snapshot_map = {s['ticker']: s for s in snapshot_data}
        except requests.exceptions.RequestException:
            snapshot_map = {}

        for stock in tracked_stocks:
            today = date.today()
            start_date = date.fromisoformat(stock['start_date'])
            days_tracked = (today - start_date).days + 1
            
            current_price = stock['start_price'] # Default value
            if stock['ticker'] in snapshot_map:
                snap = snapshot_map[stock['ticker']]
                current_price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c") or current_price

            current_change_pct = ((current_price - stock['start_price']) / stock['start_price']) * 100
            avg_daily_change_pct = current_change_pct / days_tracked

            # Fetch historical data for max swing
            max_swing = 0
            try:
                hist_url = f"https://api.polygon.io/v2/aggs/ticker/{stock['ticker']}/range/1/day/{start_date.isoformat()}/{today.isoformat()}"
                hist_resp = requests.get(hist_url, params={"apiKey": API_KEY})
                if hist_resp.status_code == 200:
                    results = hist_resp.json().get('results', [])
                    if results:
                        highs = [r['h'] for r in results]
                        lows = [r['l'] for r in results]
                        max_swing = max(highs) - min(lows)
            except requests.exceptions.RequestException:
                max_swing = 0 # API failed

            tracked_stocks_data.append({
                **stock,
                "current_price": current_price,
                "current_change_pct": current_change_pct,
                "avg_daily_change_pct": avg_daily_change_pct,
                "max_swing": max_swing,
            })

    return render_template_string(EVALUATION_TEMPLATE, stocks_to_add=stocks_to_add, tracked_stocks_data=tracked_stocks_data)

@app.route("/api/top-losers")
def api_top_losers():
    """Provides the raw JSON data for the top losers."""
    try: limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError): limit = 10
    with data_lock:
        data = TOP_LOSERS_CACHE[:limit]
    return jsonify(data)

# --- Main Execution ---
if __name__ == "__main__":
    load_common_stocks()
    app.run(host="0.0.0.0", port=10000, threaded=True)

