#!/bin/bash

echo "SQL Agent Launcher"
echo "------------------"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed."
    echo "Please install Python from https://www.python.org/downloads/"
    exit 1
fi

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not available."
    echo "Please make sure pip is installed with your Python installation."
    exit 1
fi

# Check if requirements are installed
echo "Checking dependencies..."
pip3 install -r requirements.txt

# Run the Python launch script
echo "Starting SQL Agent..."
python3 run.py
