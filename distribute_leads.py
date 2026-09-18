# distribute_leads.py
from app import app
from automation import run_distribution

if __name__ == "__main__":
    with app.app_context():
        run_distribution()