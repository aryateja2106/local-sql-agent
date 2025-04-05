#!/usr/bin/env python3
"""
SQL Agent launcher script
"""
import os
import sys
import subprocess
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_database():
    """Check if the database exists, create it if not"""
    db_path = os.getenv("DATABASE_PATH", "sales_database.db")
    if not os.path.exists(db_path):
        print("Database not found. Setting up the database...")
        subprocess.run([sys.executable, "setup_database.py"], check=True)
        print("Database setup complete!")
    else:
        print(f"Database found at {db_path}")

def check_llm_endpoint():
    """Check if the LLM endpoint is reachable"""
    import requests
    llm_url = os.getenv("LLM_API_URL", "http://127.0.0.1:1234")
    try:
        response = requests.get(f"{llm_url}/v1/models", timeout=2)
        if response.status_code == 200:
            print(f"LLM endpoint is reachable at {llm_url}")
            return True
        else:
            print(f"LLM endpoint returned status code {response.status_code}")
            return False
    except requests.exceptions.RequestException:
        print(f"LLM endpoint is not reachable at {llm_url}")
        print("Make sure LMStudio is running before starting the application.")
        return False

def launch_streamlit():
    """Launch the Streamlit application"""
    print("Starting Streamlit application...")
    subprocess.run(["streamlit", "run", "app.py"])

if __name__ == "__main__":
    print("SQL Agent Launcher")
    print("------------------")
    
    # Check and setup database
    check_database()
    
    # Check LLM endpoint
    llm_available = check_llm_endpoint()
    if not llm_available:
        response = input("LLM endpoint is not available. Start application anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Launch streamlit
    launch_streamlit()
