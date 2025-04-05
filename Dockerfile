FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x run.py
RUN chmod +x db_utils.py
RUN chmod +x test_agent.py

# Initialize the database
RUN python setup_database.py
RUN python add_user_purchase_data.py

# Set environment variables
ENV LLM_API_URL=http://host.docker.internal:1234
ENV DATABASE_PATH=sales_database.db

# Expose port for Streamlit
EXPOSE 8501

# Command to run the application
# Use purchase_behavior_app.py by default, but can be overridden with CMD in docker-compose
CMD ["streamlit", "run", "purchase_behavior_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
