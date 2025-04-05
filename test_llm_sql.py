import requests
import json
import sqlite3
import pandas as pd

# Configuration
LLM_URL = "http://127.0.0.1:1234"
DB_PATH = "sales_database.db"
MODEL_NAME = "llama-3.2-3b-instruct"  # Using the model we confirmed is available

# Connect to the database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get schema information
def get_schema_info():
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
    
    schema_info = "Database Schema:\n\n"
    
    for table in tables:
        schema_info += f"Table: {table}\n"
        
        # Get column information
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        
        schema_info += "Columns:\n"
        for col in columns:
            col_name = col[1]  # Name is at index 1
            col_type = col[2]  # Type is at index 2
            is_pk = "PRIMARY KEY" if col[5] == 1 else ""  # PK is at index 5
            schema_info += f"- {col_name} ({col_type}) {is_pk}\n"
        
        # Get sample data (first 3 rows)
        try:
            cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
            rows = cursor.fetchall()
            if rows:
                schema_info += "Sample data:\n"
                for row in rows:
                    schema_info += f"- {row}\n"
        except sqlite3.Error:
            schema_info += "Could not retrieve sample data.\n"
        
        schema_info += "\n"
    
    return schema_info

# Function to generate SQL from natural language using the LLM
def generate_sql(query, schema_info):
    system_message = f"""You are an expert SQL agent that converts natural language queries into SQL.
    
    Here is the database schema information:
    {schema_info}
    
    IMPORTANT: The database includes a user_purchase_behavior table that tracks:
    - Whether users have purchased products (has_purchased_product)
    - The likelihood of users purchasing products (purchase_likelihood)
    - Whether users have purchased services (has_purchased_service)
    - The likelihood of users purchasing services (service_purchase_likelihood)
    - The date of last interaction with the user (last_interaction_date)
    
    Your task is to:
    1. Understand the user's natural language query
    2. Generate a valid SQLite SQL query that answers the question
    3. Provide a brief explanation of what the SQL query does
    
    For queries about purchase behavior, make sure to JOIN the user_purchase_behavior table with customers to get customer names.
    
    Return ONLY a JSON object with the following structure:
    {{
        "sql_query": "THE SQL QUERY",
        "explanation": "EXPLANATION OF THE QUERY"
    }}
    """
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": query}
    ]
    
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1  # Low temperature for deterministic SQL generation
    }
    
    try:
        response = requests.post(f"{LLM_URL}/v1/chat/completions", json=payload)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        
        # Extract JSON from the response
        content = content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        
        # Try to find JSON in the content if it's not properly formatted
        try:
            # Find the first { and the last }
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                result = json.loads(json_str)
                return {
                    "sql_query": result.get("sql_query", ""),
                    "explanation": result.get("explanation", "")
                }
        except:
            pass
            
        # If we couldn't extract JSON, try to parse the whole content
        try:
            result = json.loads(content)
            return {
                "sql_query": result.get("sql_query", ""),
                "explanation": result.get("explanation", "")
            }
        except json.JSONDecodeError:
            # If we can't parse JSON, try to extract SQL query directly
            if "```sql" in content:
                sql_query = content.split("```sql")[1].split("```")[0].strip()
                explanation = "Extracted SQL query from code block"
                return {
                    "sql_query": sql_query,
                    "explanation": explanation
                }
            
            # Last resort: return an error
            return {
                "sql_query": "",
                "explanation": f"Error parsing LLM response: {content[:100]}..."
            }
    except Exception as e:
        return {
            "sql_query": "",
            "explanation": f"Error generating SQL: {str(e)}"
        }

# Function to execute SQL and return results
def execute_sql(sql_query):
    try:
        # Use pandas to execute the query and get results
        df = pd.read_sql_query(sql_query, conn)
        return {
            "success": True,
            "data": df,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }

# Test the SQL generation and execution
def test_query(natural_query):
    print(f"\n\n=== Testing Query: '{natural_query}' ===\n")
    
    # Get schema info
    schema_info = get_schema_info()
    
    # Generate SQL
    print("Generating SQL...")
    sql_response = generate_sql(natural_query, schema_info)
    
    print(f"Generated SQL: {sql_response['sql_query']}")
    print(f"Explanation: {sql_response['explanation']}")
    
    # Execute SQL if it was generated
    if sql_response['sql_query']:
        print("\nExecuting SQL...")
        result = execute_sql(sql_response['sql_query'])
        
        if result['success']:
            print("\nResults:")
            print(result['data'])
            print(f"\nReturned {len(result['data'])} rows")
        else:
            print(f"\nError executing SQL: {result['error']}")
    else:
        print("\nNo SQL query was generated.")

# Test with some example queries
test_queries = [
    "Show me all customers",
    "List users with high likelihood of purchasing services",
    "Show me customers who have purchased products but not services",
    "What are the top 5 customers by total order amount"
]

for query in test_queries:
    test_query(query)

# Close the database connection
conn.close()

print("\nTesting complete!")
