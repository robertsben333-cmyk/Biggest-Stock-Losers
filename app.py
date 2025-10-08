from flask import Flask, render_template_string, request
import requests
import json
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# --- Flask App Initialization ---
app = Flask("Identify_biggest_stocklosers")

# --- Configuration ---
API_KEY = "E3NCUMZ5jFaGCvuNr6NfyxupHpAgKiL7"

# --- In-Memory Cache for Stock Data ---
# These are populated at startup and are thread-safe.
data_lock = threading.Lock()
COMMON_STOCK_TICKERS = set()
TICKER_METADATA = {}
TOP_LOSERS_CACHE = []
LAST_UPDATED = "Not yet updated"

def load_common_stocks():
    """
    Fetches all common stock tickers from NYSE and NASDAQ once
    and stores them in global variables for fast lookups.
    """
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
                if resp.status_code != 200:
                    print(f"  [ERROR] Failed to fetch data for {exchange}. Status Code: {resp.status_code}")
                    break
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
            url = None

    print(f"--- ✅ Complete: Loaded {len(COMMON_STOCK_TICKERS)} unique common stock tickers. ---\n")


def is_cet_between_17_and_20():
    """Return True when the current time in CET is between 17:00 and 20:00."""
    cet = ZoneInfo("Europe/Paris")
    now_cet = datetime.now(timezone.utc).astimezone(cet)
    return 17 <= now_cet.hour < 20


def update_top_losers_cache(min_price=15.0):
    """
    This function runs in a background thread to fetch the latest loser data
    and update the in-memory cache.
    """
    global TOP_LOSERS_CACHE, LAST_UPDATED
    print("--- Background task: Updating top losers cache... ---")
    
    snapshot_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {"apiKey": API_KEY, "include_otc": "false"}
    
    try:
        resp = requests.get(snapshot_url, params=params)
        if resp.status_code != 200:
            print(f"  [ERROR] Failed to fetch market snapshot. Status Code: {resp.status_code}")
            return
            
        snapshot_data = resp.json().get("tickers", [])
        
    except requests.exceptions.RequestException as e:
        print(f"  [FATAL ERROR] A network error occurred while fetching snapshot: {e}")
        return

    use_prev_close_reference = is_cet_between_17_and_20()

    calculated_losers = []
    
    with data_lock:
        local_tickers = COMMON_STOCK_TICKERS.copy()
        local_metadata = TICKER_METADATA.copy()

    for snap in snapshot_data:
        ticker = snap.get("ticker", "").upper()

        if ticker not in local_tickers:
            continue

        current_price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c")

        if not current_price:
            continue

        if current_price < min_price:
            continue

        previous_close = snap.get("prevDay", {}).get("c")
        day_open = snap.get("day", {}).get("o")

        if use_prev_close_reference:
            reference_price = previous_close
        else:
            reference_price = day_open if day_open else previous_close

        if not reference_price or reference_price < min_price:
            continue

        change_pct = ((current_price - reference_price) / reference_price) * 100

        if change_pct >= 0:
            continue
            
        meta = local_metadata.get(ticker, {})
        calculated_losers.append({
            "ticker": ticker,
            "name": meta.get("name", "N/A"),
            "exchange": meta.get("exchange", "N/A"),
            "currentPrice": round(current_price, 2),
            "changePct": round(change_pct, 2),
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
        })

    sorted_losers = sorted(calculated_losers, key=lambda x: x["changePct"])
    
    with data_lock:
        TOP_LOSERS_CACHE = sorted_losers
        LAST_UPDATED = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    
    print(f"--- ✅ Background task complete: Found {len(sorted_losers)} losers. Cache updated. ---")

# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Top Stock Losers</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            font-family: 'Inter', sans-serif;
        }
        .change-negative {
            color: #ef4444; /* red-500 */
        }
    </style>
</head>
<body class="bg-gray-100 text-gray-800">
    <div class="container mx-auto px-4 py-8">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-900">Top Stock Losers</h1>
            <p class="text-gray-600 mt-2">Displaying the biggest stock decliners on NYSE & NASDAQ (Price >= $15)</p>
            <p class="text-sm text-gray-500 mt-1">Last updated: {{ last_updated }}</p>
        </header>

        <form action="/" method="GET" class="flex justify-center items-center space-x-2 sm:space-x-4 mb-8">
            <div class="flex items-center space-x-2">
                <label for="limit" class="text-sm font-medium text-gray-700">Show:</label>
                <input type="number" name="limit" id="limit" value="{{ limit }}" min="1" max="100" class="w-20 px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit" class="px-5 py-2 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-opacity-75 transition duration-200">
                Refresh
            </button>
            <a href="/api/top-losers?limit={{ limit }}" target="_blank" class="px-5 py-2 bg-gray-700 text-white font-semibold rounded-lg shadow-md hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-opacity-75 transition duration-200">
                JSON
            </a>
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
                            <td class="p-4 whitespace-nowrap">
                                <a href="{{ stock.yahooLink }}" target="_blank" class="font-bold text-blue-600 hover:underline">{{ stock.ticker }}</a>
                            </td>
                            <td class="p-4 text-gray-700">{{ stock.name }}</td>
                            <td class="p-4 text-gray-500">{{ stock.exchange }}</td>
                            <td class="p-4 text-right font-medium">${{ "%.2f"|format(stock.currentPrice) }}</td>
                            <td class="p-4 text-right font-bold change-negative">{{ "%.2f"|format(stock.changePct) }}%</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="5" class="p-8 text-center text-gray-500">
                                No significant stock losers found matching the criteria, or data is being loaded. Please refresh in a moment.
                            </td>
                        </tr>
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

JSON_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Top Stock Losers JSON</title>
    <script src=\"https://cdn.tailwindcss.com\"></script>
</head>
<body class=\"bg-gray-100 text-gray-800\">
    <div class=\"max-w-4xl mx-auto px-4 py-8\">
        <header class=\"mb-6\">
            <h1 class=\"text-3xl font-semibold text-gray-900\">Top Stock Losers – JSON</h1>
            <p class=\"text-gray-600\">Limit: {{ limit }}</p>
        </header>
        <div class=\"flex items-center gap-3 mb-4\">
            <button id=\"copy-json\" class=\"px-4 py-2 bg-blue-600 text-white rounded-lg shadow hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-400\">
                Copy JSON to clipboard
            </button>
            <span id=\"copy-status\" class=\"text-sm text-gray-500\" role=\"status\" aria-live=\"polite\"></span>
        </div>
        <pre id=\"json-output\" class=\"bg-white p-4 rounded-lg shadow overflow-x-auto text-sm text-gray-800\">{{ json_data }}</pre>
    </div>

    <script>
        (function () {
            const copyButton = document.getElementById('copy-json');
            const jsonOutput = document.getElementById('json-output');
            const status = document.getElementById('copy-status');

            function updateStatus(message, isError) {
                status.textContent = message;
                status.classList.toggle('text-red-500', Boolean(isError));
                status.classList.toggle('text-green-600', !isError);
            }

            copyButton.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(jsonOutput.textContent);
                    updateStatus('Copied!', false);
                } catch (error) {
                    updateStatus('Copy failed. Try manually selecting the text.', true);
                }
            });
        })();
    </script>
</body>
</html>
"""

# --- Flask Routes ---

@app.route("/")
def home():
    """Renders the main HTML page."""
    # Run the update in a background thread to not block the UI on first load.
    threading.Thread(target=update_top_losers_cache).start()
    
    try:
        limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError):
        limit = 10

    with data_lock:
        stocks_to_display = TOP_LOSERS_CACHE[:limit]
        last_update_time = LAST_UPDATED
    
    return render_template_string(HTML_TEMPLATE, stocks=stocks_to_display, last_updated=last_update_time, limit=limit)

@app.route("/api/top-losers")
def api_top_losers():
    """Provides the raw JSON data for the top losers."""
    try:
        limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError):
        limit = 10
    
    with data_lock:
        # We return a copy to avoid any potential race conditions if the cache is updated.
        data = TOP_LOSERS_CACHE[:limit]
    
    json_string = json.dumps(data, indent=2)
    best_match = request.accept_mimetypes.best_match(["application/json", "text/html"])
    prefers_html = request.args.get("view", "").lower() == "html" or best_match == "text/html"

    if prefers_html:
        return render_template_string(JSON_PAGE_TEMPLATE, json_data=json_string, limit=limit)

    return app.response_class(json_string, mimetype="application/json")

# --- Main Execution ---

if __name__ == "__main__":
    # Load the essential common stock data once at startup.
    load_common_stocks()
    
    # Run the Flask app.
    # Use threaded=True to handle background tasks and requests simultaneously.
    app.run(host="0.0.0.0", port=10000, threaded=True)

