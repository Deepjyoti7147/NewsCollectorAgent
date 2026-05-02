"""
api.py — REST API for managing the ticker watchlist.

Endpoints:
  • GET    /watchlist         — List all tickers
  • POST   /watchlist/<symbol> — Add a ticker
  • DELETE /watchlist/<symbol> — Remove a ticker
"""

import logging
from flask import Flask, jsonify, request

logger = logging.getLogger("news_collector.api")

def create_app(db_handler):
    """Factory to create the Flask app with the DB handler injected."""
    app = Flask(__name__)

    @app.route("/watchlist", methods=["GET"])
    def get_watchlist():
        try:
            tickers = db_handler.get_watchlist()
            return jsonify({"status": "success", "data": [t["symbol"] for t in tickers]})
        except Exception as exc:
            logger.error("API error (GET /watchlist): %s", exc)
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/watchlist/<symbol>", methods=["POST"])
    def add_ticker(symbol):
        try:
            added = db_handler.add_to_watchlist(symbol)
            if added:
                return jsonify({"status": "success", "message": f"Added {symbol} to watchlist"})
            else:
                return jsonify({"status": "success", "message": f"{symbol} was already in watchlist or invalid"})
        except Exception as exc:
            logger.error("API error (POST /watchlist/%s): %s", symbol, exc)
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/watchlist/<symbol>", methods=["DELETE"])
    def remove_ticker(symbol):
        try:
            removed = db_handler.remove_from_watchlist(symbol)
            if removed:
                return jsonify({"status": "success", "message": f"Removed {symbol} from watchlist"})
            else:
                return jsonify({"status": "error", "message": f"{symbol} not found in watchlist"}), 404
        except Exception as exc:
            logger.error("API error (DELETE /watchlist/%s): %s", symbol, exc)
            return jsonify({"status": "error", "message": str(exc)}), 500

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "NewsCollectorAgent API"})

    return app
