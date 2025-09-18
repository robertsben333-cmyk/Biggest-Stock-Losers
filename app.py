from flask import Flask, jsonify, render_template_string, request
import requests

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

def get_top_losers(limit=10):
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
        change_pct = snap.get("todaysChangePerc")
        if change_pct is None or change_pct >= 0:
            continue
        meta = ticker_metadata.get(ticker, {})
        losers.append({
            "ticker": ticker,
            "name": meta.get("name", ""),
            "exchange": meta.get("exchange", ""),
            "currentPrice": round(price, 2),
            "changePct": round(change_pct, 2),
            "yahooLink": f"https://finance.yahoo.com/quote/{ticker}",
            "sparkline": f"https://chart.yahoo.com/z?s={ticker}&t=5d&q=l&l=on&z=s&p=m50,m200"
        })

    return sorted(losers, key=lambda x: x["changePct"])[:limit]

@app.route("/", methods=["GET"])
def homepage():
    try:
        limit = int(request.args.get("limit", 10))
        losers = get_top_losers(limit=limit)

        html = """
        <html>
        <head>
            <title>Top Stock Losers</title>
            <style>
                body {
                    font-family: 'Segoe UI', sans-serif;
                    background: #f4f6f8;
                    padding: 30px;
                    color: #333;
                }
                h1 {
                    color: #1e2a38;
                    margin-bottom: 10px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
                }
                th, td {
                    padding: 12px;
                    border: 1px solid #ddd;
                    text-align: center;
                }
                th {
                    background-color: #2e3a59;
                    color: #fff;
                    cursor: pointer;
                }
                tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                tr:hover {
                    background-color: #eef1f4;
                }
                .negative {
                    color: red;
                    font-weight: bold;
                }
                .input-box {
                    margin-top: 20px;
                }
                input[type="number"] {
                    padding: 6px 10px;
                    font-size: 16px;
                    width: 80px;
                }
                button {
                    padding: 7px 14px;
                    font-size: 16px;
                    background-color: #2e3a59;
                    color: white;
                    border: none;
                    cursor: pointer;
                }
                button:hover {
                    background-color: #3f4d6a;
                }
            </style>
            <script>
                function sortTable(n) {
                    const table = document.getElementById("losersTable");
                    let switching = true;
                    let dir = "desc";
                    let switchcount = 0;

                    while (switching) {
                        switching = false;
                        const rows = table.rows;
                        for (let i = 1; i < (rows.length - 1); i++) {
                            let shouldSwitch = false;
                            const x = rows[i].getElementsByTagName("TD")[n];
                            const y = rows[i + 1].getElementsByTagName("TD")[n];

                            let xVal = x.innerHTML;
                            let yVal = y.innerHTML;

                            if (!isNaN(parseFloat(xVal))) {
                                xVal = parseFloat(xVal);
                                yVal = parseFloat(yVal);
                            }

                            if (dir == "asc") {
                                if (xVal > yVal) {
                                    shouldSwitch = true;
                                    break;
                                }
                            } else if (dir == "desc") {
                                if (xVal < yVal) {
                                    shouldSwitch = true;
                                    break;
                                }
                            }
                        }
                        if (shouldSwitch) {
                            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                            switching = true;
                            switchcount++;
                        } else {
                            if (switchcount == 0 && dir == "desc") {
                                dir = "asc";
                                switching = true;
                            }
                        }
                    }
                }

                function updateLimit() {
                    const val = document.getElementById("limitInput").value;
                    if (val > 0) {
                        window.location.href = `/?limit=${val}`;
                    }
                }
            </script>
        </head>
        <body>
            <h1>📉 Top {{ limit }} Biggest Stock Losers (Price ≥ $15)</h1>
            <div class="input-box">
                Show
                <input type="number" id="limitInput" value="{{ limit }}" min="1" />
                stocks
                <button onclick="updateLimit()">Update</button>
            </div>
            <table id="losersTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Ticker</th>
                        <th onclick="sortTable(1)">Name</th>
                        <th onclick="sortTable(2)">Exchange</th>
                        <th onclick="sortTable(3)">Price ($)</th>
                        <th onclick="sortTable(4)">Change %</th>
                        <th>Chart</th>
                    </tr>
                </thead>
                <tbody>
                    {% for stock in losers %}
                    <tr>
                        <td><a href="{{ stock.yahooLink }}" target="_blank">{{ stock.ticker }}</a></td>
                        <td>{{ stock.name }}</td>
                        <td>{{ stock.exchange }}</td>
                        <td>{{ stock.currentPrice }}</td>
                        <td class="negative">{{ stock.changePct }}%</td>
                        <td><a href="{{ stock.yahooLink }}" target="_blank"><img src="{{ stock.sparkline }}" width="120" height="40" alt="sparkline" /></a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """
        return render_template_string(html, losers=losers, limit=limit)
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route("/top-losers", methods=["GET"])
def api_top_losers():
    try:
        limit = int(request.args.get("limit", 10))
        return jsonify(get_top_losers(limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
