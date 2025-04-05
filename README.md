# Local SQL Agent

A Python-based SQL agent that converts natural language queries into SQL commands, executes them against a SQLite database, and returns the results. The agent uses a local LLM (Language Model) to understand natural language and generate appropriate SQL queries.

## Features

- Natural language to SQL conversion using a local LLM (with LMStudio or Ollama)
- SQLite database integration with sample sales data
- Interactive Streamlit web interface
- Query execution and result visualization
- Explanation of generated SQL queries
- CSV export functionality
- Database utilities for inspection and maintenance

## Project Structure

- `purchase_behavior_app.py`: Streamlit web application for user purchase behavior analysis
- `app.py`: Standard Streamlit web application for general SQL queries
- `models.py`: Pydantic models for the application
- `llm_client.py`: Client for communicating with the LLM API (supports both LMStudio and Ollama)
- `sql_agent.py`: Core SQL agent functionality
- `setup_database.py`: Script to set up the SQLite database with dummy data
- `add_user_purchase_data.py`: Script to add user purchase behavior data
- `db_utils.py`: Utility functions for database management
- `run.py`: Launcher script for the application
- `test_agent.py`: Test script for the SQL agent
- `Dockerfile` & `docker-compose.yml`: Docker configuration for containerization

## Prerequisites

- Python 3.7+
- One of the following local LLM solutions:
  - [LMStudio](https://lmstudio.ai/) with a local model running at http://127.0.0.1:1234
  - [Ollama](https://ollama.ai/) with a model like llama3 running at http://127.0.0.1:11434
- SQLite (included with Python)

## Setup and Installation

### Local Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/aryateja2106/local-sql-agent.git
   cd local-sql-agent
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # OR
   venv\Scripts\activate  # On Windows
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up the database:
   ```bash
   python setup_database.py
   python add_user_purchase_data.py
   ```

5. Create a `.env` file based on the example:
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file to configure your LLM provider (LMStudio or Ollama)

6. Start your local LLM:
   - For LMStudio: Start the application and ensure it's running at http://127.0.0.1:1234
   - For Ollama: Install Ollama and run `ollama run llama3` (or your preferred model)

7. Run the Streamlit application using one of these methods:
   
   - Using the run script (recommended):
     ```bash
     python run.py
     ```
   
   - Direct Streamlit command for purchase behavior analysis:
     ```bash
     streamlit run purchase_behavior_app.py
     ```
   
   - Direct Streamlit command for standard SQL queries:
     ```bash
     streamlit run app.py
     ```

### Docker Installation

1. Make sure Docker and Docker Compose are installed on your system

2. Clone this repository:
   ```bash
   git clone https://github.com/aryateja2106/local-sql-agent.git
   cd local-sql-agent
   ```

3. Start your local LLM:
   - For LMStudio: Start the application and ensure it's running
   - For Ollama: Install Ollama and run `ollama run llama3` (or your preferred model)

4. Edit the `docker-compose.yml` file to configure your LLM provider:
   - For LMStudio (default): Use `LLM_API_URL=http://host.docker.internal:1234`
   - For Ollama: Use `LLM_API_URL=http://host.docker.internal:11434` and uncomment the `LLM_MODEL` line

5. Build and start the container:
   ```bash
   docker-compose up -d
   ```

6. Access the application at http://localhost:8501

   Note: When using Docker, make sure your LLM is accessible from the container via `host.docker.internal`

### Quick Start with Docker (One-Line Command)

If you have Docker installed and your LLM running, you can start the application with a single command:

```bash
docker run -p 8501:8501 -e LLM_API_URL=http://host.docker.internal:1234 $(docker build -q .)
```

For Ollama:
```bash
docker run -p 8501:8501 -e LLM_API_URL=http://host.docker.internal:11434 -e LLM_MODEL=llama3 $(docker build -q .)
```

## Usage

1. Enter a natural language query in the text area
2. Click "Run Query" to process the query
3. View the generated SQL, explanation, and results
4. Download the results as a CSV file if needed

### Example Queries for Purchase Behavior Analysis

- "Show me customers who have purchased products but not services"
- "List users with high likelihood of purchasing services"
- "Find customers who haven't purchased anything but have high purchase likelihood"
- "Show me the top 5 customers most likely to purchase both products and services"
- "Which customers had their last interaction in the past 30 days and have a high purchase likelihood?"

### Example Queries for Standard SQL Analysis

- "Show me the top 5 customers by total order amount"
- "What are the most popular products in the Electronics category?"
- "How many orders were placed in the last 6 months?"
- "Which customers have not placed any orders?"
- "What is the average order value by product category?"

## Database Utilities

The project includes a database utility script (`db_utils.py`) for database management:

```bash
# Run an interactive SQL session
python db_utils.py interactive sales_database.db

# Export database schema to JSON
python db_utils.py export_schema sales_database.db schema.json

# Export query results to CSV
python db_utils.py export_query sales_database.db "SELECT * FROM customers" customers.csv

# Import CSV data to a table
python db_utils.py import_csv sales_database.db new_products.csv products
```

## Testing

Run the test script to verify the functionality:

```bash
python test_agent.py
```

## Environment Variables

The application uses the following environment variables that can be set in the `.env` file:

- `LLM_API_URL`: URL of the LLM API
  - For LMStudio: `http://127.0.0.1:1234` (default)
  - For Ollama: `http://127.0.0.1:11434`
- `LLM_MODEL`: Model name to use (especially important for Ollama)
  - Default for Ollama: `llama3`
  - Default for LMStudio: `deepseek-r1-distill-qwen-14b`
- `DATABASE_PATH`: Path to the SQLite database (default: `sales_database.db`)

## License

This project is licensed under the MIT License - see the LICENSE file for details.
