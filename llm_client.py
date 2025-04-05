import requests
import json
import time
import os
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

class LLMClient:
    """Client for interacting with LLM APIs (LMStudio or Ollama)"""
    
    def __init__(self, base_url: str = None):
        # Load environment variables
        load_dotenv()
        
        # Get base URL from parameter, environment, or default
        self.base_url = base_url or os.getenv("LLM_API_URL", "http://127.0.0.1:1234")
        self.chat_endpoint = f"{self.base_url}/v1/chat/completions"
        
        # Determine if using Ollama based on port (11434)
        self.is_ollama = "11434" in self.base_url
        
        # Set model name based on provider
        if self.is_ollama:
            self.model_name = os.getenv("LLM_MODEL", "llama3")
            print(f"Using Ollama with model: {self.model_name}")
        else:
            self.model_name = os.getenv("LLM_MODEL", "deepseek-r1-distill-qwen-14b")
            print(f"Using LMStudio with model: {self.model_name}")
    
    def get_completion(self, 
                     messages: List[Dict[str, str]], 
                     temperature: float = 0.7,
                     max_tokens: int = 1000) -> Dict[str, Any]:
        """
        Get a completion from the LLM
        
        Args:
            messages: List of message dictionaries in the format {"role": "user"/"system", "content": "message"}
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The completion response
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(self.chat_endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error communicating with LLM API: {str(e)}")
    
    def _extract_sql_from_response(self, content: str) -> Dict[str, str]:
        """
        Extract SQL query and explanation from LLM response content
        
        Args:
            content: Response content from LLM
            
        Returns:
            Dictionary with SQL query and explanation
        """
        # Try to extract JSON from the response
        content = content.strip()
        
        # Method 1: Extract from JSON code block
        if "```json" in content:
            try:
                json_content = content.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_content)
                if "sql_query" in result and "explanation" in result:
                    return {
                        "sql_query": result.get("sql_query", ""),
                        "explanation": result.get("explanation", "")
                    }
            except:
                pass
                
        # Method 2: Extract from any code block
        elif "```" in content:
            try:
                code_content = content.split("```")[1].split("```")[0].strip()
                if code_content.lower().startswith("sql"):
                    sql_query = code_content[3:].strip()
                    explanation = "Extracted SQL query from code block"
                    return {
                        "sql_query": sql_query,
                        "explanation": explanation
                    }
                else:
                    sql_query = code_content
                    explanation = "Extracted SQL query from code block"
                    return {
                        "sql_query": sql_query,
                        "explanation": explanation
                    }
            except:
                pass
        
        # Method 3: Find JSON object in the content
        try:
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                result = json.loads(json_str)
                if "sql_query" in result and "explanation" in result:
                    return {
                        "sql_query": result.get("sql_query", ""),
                        "explanation": result.get("explanation", "")
                    }
        except:
            pass
            
        # Method 4: Try to parse the whole content as JSON
        try:
            result = json.loads(content)
            if "sql_query" in result and "explanation" in result:
                return {
                    "sql_query": result.get("sql_query", ""),
                    "explanation": result.get("explanation", "")
                }
        except:
            pass
            
        # Method 5: Look for SQL keywords to extract a query
        if "SELECT" in content.upper() or "FROM" in content.upper():
            lines = content.split('\n')
            sql_lines = []
            capture = False
            
            for line in lines:
                if "SELECT" in line.upper() or capture:
                    capture = True
                    sql_lines.append(line)
                    if ";" in line:
                        break
            
            if sql_lines:
                sql_query = ' '.join(sql_lines).strip()
                if sql_query.endswith(';'):
                    sql_query = sql_query[:-1]  # Remove trailing semicolon
                explanation = "Extracted SQL query from text"
                return {
                    "sql_query": sql_query,
                    "explanation": explanation
                }
        
        # Last resort: return an error
        return {
            "sql_query": "",
            "explanation": f"Error parsing LLM response: {content[:100]}..."
        }
    
    def generate_sql(self, query: str, schema_info: str, error_message: str = None) -> Dict[str, str]:
        """
        Generate SQL from a natural language query
        
        Args:
            query: Natural language query
            schema_info: Database schema information
            error_message: Optional error message from previous SQL execution attempt
            
        Returns:
            Dictionary with SQL query and explanation
        """
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
        
        IMPORTANT RULES FOR GENERATING SQL:
        - Use only tables and columns that exist in the schema
        - Make sure all column references in JOINs are fully qualified (e.g., customers.customer_id)
        - For boolean values in SQLite, use 0 for false and 1 for true
        - Ensure all SQL syntax is compatible with SQLite
        - Do not use double quotes for string literals, use single quotes
        - Do not use aliases without the AS keyword
        - Make sure all parentheses are properly closed
        - Do not use functions that don't exist in SQLite
        
        Return ONLY a JSON object with the following structure:
        {{
            "sql_query": "THE SQL QUERY",
            "explanation": "EXPLANATION OF THE QUERY"
        }}
        """
        
        user_message = query
        if error_message:
            user_message += f"\n\nThe previous SQL query failed with the following error: {error_message}\nPlease fix the SQL query and try again."
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        
        try:
            response = self.get_completion(messages, temperature=0.1)  # Low temperature for deterministic SQL generation
            content = response['choices'][0]['message']['content']
            return self._extract_sql_from_response(content)
        except Exception as e:
            return {
                "sql_query": "",
                "explanation": f"Error generating SQL: {str(e)}"
            }
    
    def improve_sql(self, query: str, schema_info: str, original_sql: str, error_message: str) -> Dict[str, str]:
        """
        Improve a SQL query that failed with an error
        
        Args:
            query: Original natural language query
            schema_info: Database schema information
            original_sql: The SQL query that failed
            error_message: Error message from SQL execution
            
        Returns:
            Dictionary with improved SQL query and explanation
        """
        system_message = f"""You are an expert SQL agent that fixes broken SQL queries.
        
        Here is the database schema information:
        {schema_info}
        
        The user asked: "{query}"
        
        The following SQL query was generated but failed with an error:
        ```sql
        {original_sql}
        ```
        
        Error message: {error_message}
        
        Your task is to:
        1. Analyze the error message and the original SQL query
        2. Fix the SQL query to make it work with SQLite
        3. Provide a brief explanation of what was wrong and how you fixed it
        
        IMPORTANT RULES FOR FIXING SQL:
        - Use only tables and columns that exist in the schema
        - Make sure all column references in JOINs are fully qualified (e.g., customers.customer_id)
        - For boolean values in SQLite, use 0 for false and 1 for true
        - Ensure all SQL syntax is compatible with SQLite
        - Do not use double quotes for string literals, use single quotes
        - Do not use aliases without the AS keyword
        - Make sure all parentheses are properly closed
        - Do not use functions that don't exist in SQLite
        
        Return ONLY a JSON object with the following structure:
        {{
            "sql_query": "THE FIXED SQL QUERY",
            "explanation": "EXPLANATION OF THE FIXES"
        }}
        """
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": "Please fix the SQL query."}
        ]
        
        try:
            response = self.get_completion(messages, temperature=0.1)
            content = response['choices'][0]['message']['content']
            return self._extract_sql_from_response(content)
        except Exception as e:
            return {
                "sql_query": "",
                "explanation": f"Error improving SQL: {str(e)}"
            }
