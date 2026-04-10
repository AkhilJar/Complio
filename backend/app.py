from config import app  # Flask app object created in config.py
import routes           # importing routes.py registers all @app.route decorators

if __name__ == "__main__":
    app.run(debug=app.config["FLASK_DEBUG"], port=5001)
