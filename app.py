from flask import Flask
from services import load_common_stocks, update_top_losers_cache
import threading

# --- Flask App Initialization ---
app = Flask("Identify_biggest_stocklosers")

# Import routes after app is created to avoid circular imports
import routes

if __name__ == "__main__":
    # Load the essential common stock data once at startup.
    print("Starting initial data load...")
    load_common_stocks()
    
    # Perform the first cache update on startup.
    update_top_losers_cache()
    print("Initial data load complete. Starting web server.")
    
    # Run the Flask app.
    # Use threaded=True to handle background tasks and requests simultaneously.
    app.run(host="0.0.0.0", port=10000, threaded=True)

