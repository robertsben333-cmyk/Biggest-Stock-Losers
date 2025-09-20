from flask import render_template, request, jsonify, redirect, url_for
from app import app
from services import (
    get_top_losers_from_cache, 
    update_top_losers_cache, 
    get_last_update_time, 
    get_evaluation_data,
    add_stocks_to_tracker
)
import threading

@app.route("/")
def home():
    """Renders the main homepage."""
    # Trigger a background refresh of the data.
    threading.Thread(target=update_top_losers_cache).start()
    
    try:
        limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError):
        limit = 10

    stocks_to_display = get_top_losers_from_cache(limit)
    last_update_time = get_last_update_time()
    
    return render_template("home.html", stocks=stocks_to_display, last_updated=last_update_time, limit=limit)

@app.route("/evaluation", methods=['GET', 'POST'])
def evaluation():
    """Renders the evaluation page and handles adding/removing stocks."""
    if request.method == 'POST':
        # Logic to add or remove stocks from the tracker
        if 'track_ticker' in request.form:
            tickers_to_track = request.form.getlist('track_ticker')
            add_stocks_to_tracker(tickers_to_track)
        
        if 'untrack_ticker' in request.form:
            # Although not in the original request, adding a way to remove stocks is good practice.
            # ticker_to_untrack = request.form.get('untrack_ticker')
            # remove_stock_from_tracker(ticker_to_untrack)
            pass # Placeholder for remove logic
            
        return redirect(url_for('evaluation'))

    # For a GET request, fetch all necessary data for the page
    stocks_to_add, tracked_stocks_data = get_evaluation_data()

    return render_template("evaluation.html", stocks_to_add=stocks_to_add, tracked_stocks_data=tracked_stocks_data)

@app.route("/api/top-losers")
def api_top_losers():
    """Provides the raw JSON data for the top losers."""
    try:
        limit = int(request.args.get("limit", 10))
    except (ValueError, TypeError):
        limit = 10
    
    data = get_top_losers_from_cache(limit)
    return jsonify(data)
