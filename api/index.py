import sys
import os

# Add root directory to python path for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app

# Vercel serverless function entrypoint
if __name__ == "__main__":
    app.run()
