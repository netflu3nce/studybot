"""
Keep-alive web server.

Render's free Web Service spins down when idle. UptimeRobot pings the URL
every few minutes to keep it awake. This Flask app runs in a background
thread alongside the bot's polling loop.
"""

import os
from threading import Thread
from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "GST 102 Study Bot is alive ✅", 200


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def _run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    Thread(target=_run, daemon=True).start()
