from flask import Flask
from flask_cors import CORS
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load variables from .env into os.environ before anything else reads them.
load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])
# CORS (Cross-Origin Resource Sharing) — browsers block requests between
# different origins by default (Same-Origin Policy).
# This tells Flask to allow requests from our React dev server only.

# Store config in Flask's built-in config dict so any file that imports
# `app` can read settings via app.config["KEY"] instead of calling
# os.getenv() in multiple places.
app.config["DATABASE_URL"]    = os.getenv("DATABASE_URL")
app.config["OPENAI_API_KEY"]  = os.getenv("OPENAI_API_KEY")
app.config["FLASK_DEBUG"]     = os.getenv("FLASK_DEBUG", "0") == "1"

# One shared OpenAI client for the whole app.
# Creating it here (not inside each route function) is more efficient —
# the client sets up an HTTP session once and reuses it.
openai_client = OpenAI(api_key=app.config["OPENAI_API_KEY"])

# Max number of previous messages sent to OpenAI per request.
# Keeps token costs predictable — gpt-4o-mini charges per token used.
MAX_HISTORY = 20
