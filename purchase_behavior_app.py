import streamlit as st
import pandas as pd
import os
import subprocess
import sys
import traceback
from dotenv import load_dotenv

from sql_agent import SQLAgent
from llm_client import LLMClient

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(page_title="SQL Agent - User Purchase Behavior", layout="wide")

# Sidebar
st.sidebar.title("SQL Agent")
st.sidebar.info(
    "This application uses an LLM to analyze user purchase behavior "
    "and predict future purchases based on natural language queries."
)

# Database file path
DB_PATH = "sales_database.db"

# Check if database exists, create it if it doesn't
if not os.path.exists(DB_PATH):
    st.sidebar.warning("Database not found. Setting up the database...")
    try:
        subprocess.run([sys.executable, "setup_database.py"], check=True)
        subprocess.run([sys.executable, "add_user_purchase_data.py"], check=True)
        st.sidebar.success("Database setup complete!")
    except subprocess.CalledProcessError as e:
        st.sidebar.error(f"Error setting up database: {str(e)}")

# LLM Client configuration
llm_url = st.sidebar.text_input("LLM API URL", value="http://127.0.0.1:1234")
st.sidebar.caption("Make sure your LLM Studio is running at this URL")

# Set number of retries
max_retries = st.sidebar.slider("Max SQL improvement attempts", min_value=1, max_value=5, value=3)

# Check if the LLM endpoint is reachable
import requests
try:
    response = requests.get(f"{llm_url}/v1/models", timeout=2)
    if response.status_code == 200:
        models = response.json().get('data', [])
        model_names = [model.get('id') for model in models]
        if 'deepseek-r1-distill-qwen-14b' in model_names:
            st.sidebar.success(" deepseek-r1-distill-qwen-14b model is available")
        else:
            st.sidebar.warning(" deepseek-r1-distill-qwen-14b model not found. Available models: " + ", ".join(model_names))
    else:
        st.sidebar.error(f"LLM endpoint returned status code {response.status_code}")
except requests.exceptions.RequestException:
    st.sidebar.error("LLM endpoint is not reachable. Make sure LLM Studio is running.")

# Initialize the LLM client and SQL Agent
try:
    llm_client = LLMClient(base_url=llm_url)
    sql_agent = SQLAgent(DB_PATH, llm_client, max_retries=max_retries)
except Exception as e:
    st.error(f"Error initializing SQL Agent: {str(e)}")
    st.stop()

# Main content
st.title("User Purchase Behavior Analysis")
st.subheader("Ask questions about user purchase behavior in natural language")

# Example queries
st.caption("Example queries:")
examples = [
    "Show me customers who have purchased products but not services",
    "List users with high likelihood of purchasing services",
    "Find customers who haven't purchased anything but have high purchase likelihood",
    "Show me the top 5 customers most likely to purchase both products and services",
    "Which customers had their last interaction in the past 30 days and have a high purchase likelihood?"
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
                
                # Display improvement history if available
                if response.improvement_history:
                    with st.expander("SQL Improvement Attempts", expanded=True):
                        for attempt in response.improvement_history:
                            st.markdown(f"**Attempt {attempt.attempt}**")
                            st.code(attempt.sql, language="sql")
                            st.error(f"Error: {attempt.error}")
                            st.markdown("---")
                
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
                        
                        # Visualize data if it contains purchase likelihood
                        if 'purchase_likelihood' in df.columns or 'service_purchase_likelihood' in df.columns:
                            st.subheader("Visualization:")
                            
                            if 'purchase_likelihood' in df.columns and 'service_purchase_likelihood' in df.columns:
                                chart_data = df[['purchase_likelihood', 'service_purchase_likelihood']]
                                if 'customer_name' in df.columns or 'name' in df.columns:
                                    chart_data.index = df['customer_name'] if 'customer_name' in df.columns else df['name']
                                st.bar_chart(chart_data)
                            elif 'purchase_likelihood' in df.columns:
                                chart_data = df[['purchase_likelihood']]
                                if 'customer_name' in df.columns or 'name' in df.columns:
                                    chart_data.index = df['customer_name'] if 'customer_name' in df.columns else df['name']
                                st.bar_chart(chart_data)
                            elif 'service_purchase_likelihood' in df.columns:
                                chart_data = df[['service_purchase_likelihood']]
                                if 'customer_name' in df.columns or 'name' in df.columns:
                                    chart_data.index = df['customer_name'] if 'customer_name' in df.columns else df['name']
                                st.bar_chart(chart_data)
                        
            except Exception as e:
                st.error(f"Error processing query: {str(e)}")
                st.error(traceback.format_exc())

# Database schema information
with st.expander("View Database Schema"):
    st.code(sql_agent.schema_info)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("SQL Agent powered by LLM Studio using deepseek-r1-distill-qwen-14b")
