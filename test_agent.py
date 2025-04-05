#!/usr/bin/env python3
"""
Test script for SQL Agent
"""
import os
import sys
import json
from dotenv import load_dotenv

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from llm_client import LLMClient
from sql_agent import SQLAgent
from models import SQLGenerationRequest

# Load environment variables
load_dotenv()

def test_sql_generation():
    """Test SQL generation functionality"""
    # Set up clients
    llm_url = os.getenv("LLM_API_URL", "http://127.0.0.1:1234")
    db_path = os.getenv("DATABASE_PATH", "sales_database.db")
    
    print(f"Connecting to LLM at {llm_url}")
    llm_client = LLMClient(base_url=llm_url)
    
    print(f"Connecting to database at {db_path}")
    sql_agent = SQLAgent(db_path, llm_client)
    
    # Test queries
    test_queries = [
        "Show me all customers",
        "What are the top 5 most expensive products?",
        "How many orders does each customer have?",
        "What is the total revenue by product category?",
        "Which customer spent the most money?"
    ]
    
    for query in test_queries:
        print(f"\nTesting query: '{query}'")
        
        # Generate SQL
        try:
            request = SQLGenerationRequest(query=query)
            sql_response = sql_agent.generate_sql(request)
            
            print("Generated SQL:")
            print(sql_response.sql_query)
            print("\nExplanation:")
            print(sql_response.explanation)
            
            # Execute SQL
            result, error = sql_agent.execute_sql(sql_response.sql_query)
            
            if error:
                print(f"\nError executing SQL: {error}")
            else:
                print(f"\nExecution successful, returned {result.row_count} rows")
                if result.row_count > 0:
                    print("\nColumns:")
                    print(result.columns)
                    print("\nFirst row:")
                    print(result.rows[0] if result.rows else "No rows")
        except Exception as e:
            print(f"Error processing query: {str(e)}")
    
    # Close the database connection
    sql_agent.close()
    print("\nTests completed")

def test_full_agent():
    """Test the full agent functionality"""
    # Set up clients
    llm_url = os.getenv("LLM_API_URL", "http://127.0.0.1:1234")
    db_path = os.getenv("DATABASE_PATH", "sales_database.db")
    
    print(f"Connecting to LLM at {llm_url}")
    llm_client = LLMClient(base_url=llm_url)
    
    print(f"Connecting to database at {db_path}")
    sql_agent = SQLAgent(db_path, llm_client)
    
    # Test a query with the full agent
    test_query = "Show me the customers who spent more than $500 in total"
    
    print(f"\nTesting full agent with query: '{test_query}'")
    
    try:
        response = sql_agent.process_query(test_query)
        
        print("Natural Query:")
        print(response.natural_query)
        
        print("\nGenerated SQL:")
        print(response.generated_sql)
        
        print("\nExplanation:")
        print(response.explanation)
        
        if response.error:
            print(f"\nError: {response.error}")
        elif response.query_result:
            print(f"\nResults ({response.query_result.row_count} rows):")
            print("Columns:", response.query_result.columns)
            
            # Print up to 5 rows
            for i, row in enumerate(response.query_result.rows[:5]):
                print(f"Row {i+1}:", row)
                
            if response.query_result.row_count > 5:
                print(f"... and {response.query_result.row_count - 5} more rows")
    except Exception as e:
        print(f"Error in full agent test: {str(e)}")
    
    # Close the database connection
    sql_agent.close()
    print("\nFull agent test completed")

if __name__ == "__main__":
    print("SQL Agent Test Suite")
    print("-------------------")
    
    # Check if database exists
    db_path = os.getenv("DATABASE_PATH", "sales_database.db")
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. Please run setup_database.py first.")
        sys.exit(1)
    
    # Run tests
    test_option = input("Select test to run:\n1. SQL Generation Test\n2. Full Agent Test\n3. Both Tests\nChoice (1-3): ")
    
    if test_option == "1":
        test_sql_generation()
    elif test_option == "2":
        test_full_agent()
    elif test_option == "3":
        test_sql_generation()
        print("\n" + "-" * 50 + "\n")
        test_full_agent()
    else:
        print("Invalid option selected")
