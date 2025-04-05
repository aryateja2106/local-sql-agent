import streamlit as st
import pandas as pd
import os
import subprocess
import sys
import traceback

from sql_agent import SQLAgent
from llm_client import LLMClient

# Page configuration
st.set_page_config(page_title="SQL Agent", layout="wide")

# Sidebar
st.sidebar.title("SQL Agent")
st.sidebar.info(
    "This application uses an LLM to convert natural language queries "
    "into SQL and execute them against a SQLite database."
)

# Database file path
DB_PATH = "sales_database.db"

# Check if database exists, create it if it doesn't
if not os.path.exists(DB_PATH):
    st.sidebar.warning("Database not found. Setting up the database...")
    try:
        subprocess.run([sys.executable, "setup_database.py"], check=True)
        st.sidebar.success("Database setup complete!")
    except subprocess.CalledProcessError as e:
        st.sidebar.error(f"Error setting up database: {str(e)}")

# LLM Client configuration
llm_url = st.sidebar.text_input("LLM API URL", value="http://127.0.0.1:1234")
st.sidebar.caption("Make sure your LLM Studio is running at this URL")

# Check if the LLM endpoint is reachable
import requests
try:
    response = requests.get(f"{llm_url}/v1/models", timeout=2)
    if response.status_code == 200:
        st.sidebar.success("LLM endpoint is reachable")
    else:
        st.sidebar.error(f"LLM endpoint returned status code {response.status_code}")
except requests.exceptions.RequestException:
    st.sidebar.error("LLM endpoint is not reachable. Make sure LLM Studio is running.")

# Initialize the LLM client and SQL Agent
try:
    llm_client = LLMClient(base_url=llm_url)
    sql_agent = SQLAgent(DB_PATH, llm_client)
except Exception as e:
    st.error(f"Error initializing SQL Agent: {str(e)}")
    st.stop()

# Main content
st.title("SQL Agent")
st.subheader("Ask questions about the sales database in natural language")

# Example queries
st.caption("Example queries:")
examples = [
    "Show me the top 5 customers by total order amount",
    "What are the most popular products in the Electronics category?",
    "How many orders were placed in the last 6 months?",
    "Which customers have not placed any orders?",
    "What is the average order value by product category?"
]
for ex in examples:
    if st.button(ex):
        st.session_state.query = ex

# Input box for the query
query = st.text_area("Enter your query:", height=100, key="query")

# Submit button
if st.button("Run Query"):
    if not query:
        st.warning("Please enter a query.")
    else:
        with st.spinner("Processing query..."):
            try:
                # Process the query
                response = sql_agent.process_query(query)
                
                # Display the generated SQL
                st.subheader("Generated SQL:")
                st.code(response.generated_sql, language="sql")
                
                # Display the explanation
                st.subheader("Explanation:")
                st.write(response.explanation)
                
                # Display the results or error
                if response.error:
                    st.error(f"Error executing SQL: {response.error}")
                elif response.query_result:
                    st.subheader("Results:")
                    if response.query_result.row_count == 0:
                        st.info("Query returned no results.")
                    else:
                        # Convert to DataFrame for better display
                        df = pd.DataFrame(
                            response.query_result.rows, 
                            columns=response.query_result.columns
                        )
                        st.dataframe(df)
                        st.caption(f"Returned {response.query_result.row_count} rows")
                        
                        # Option to download results as CSV
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="Download results as CSV",
                            data=csv,
                            file_name="query_results.csv",
                            mime="text/csv"
                        )
            except Exception as e:
                st.error(f"Error processing query: {str(e)}")
                st.error(traceback.format_exc())

# Database schema information
with st.expander("View Database Schema"):
    st.code(sql_agent.schema_info)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("SQL Agent powered by LLM Studio")
