from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class SQLGenerationRequest(BaseModel):
    """Request model for generating SQL queries from natural language"""
    query: str = Field(..., description="Natural language query from the user")
    context: Optional[str] = Field(None, description="Additional context for the query")

class SQLGenerationResponse(BaseModel):
    """Response model for SQL generation"""
    sql_query: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of the SQL query")
    
class SQLQueryResult(BaseModel):
    """Model to represent SQL query results"""
    columns: List[str] = Field(..., description="Column names of the result")
    rows: List[List[Any]] = Field(..., description="Rows of data from the result")
    row_count: int = Field(..., description="Number of rows returned")
    
class UserPurchaseBehavior(BaseModel):
    """Model to represent user purchase behavior"""
    user_id: int = Field(..., description="Unique identifier for the user")
    customer_id: int = Field(..., description="Reference to the customer table")
    has_purchased_product: bool = Field(..., description="Whether the user has purchased a product")
    purchase_likelihood: float = Field(..., description="Likelihood of the user purchasing a product (0-1)")
    has_purchased_service: bool = Field(..., description="Whether the user has purchased a service")
    service_purchase_likelihood: float = Field(..., description="Likelihood of the user purchasing a service (0-1)")
    last_interaction_date: str = Field(..., description="Date of the last interaction with the user")

class SQLImprovementAttempt(BaseModel):
    """Model to represent an SQL improvement attempt"""
    attempt: int = Field(..., description="Attempt number")
    sql: str = Field(..., description="SQL query that was attempted")
    error: str = Field(..., description="Error message from the attempt")

class SQLAgentResponse(BaseModel):
    """Complete response from the SQL agent"""
    natural_query: str = Field(..., description="Original natural language query")
    generated_sql: str = Field(..., description="SQL query that was generated")
    explanation: str = Field(..., description="Explanation of what the SQL query does")
    query_result: Optional[SQLQueryResult] = Field(None, description="Results of executing the SQL query")
    error: Optional[str] = Field(None, description="Error message if query execution failed")
    user_purchase_behavior: Optional[UserPurchaseBehavior] = Field(None, description="User purchase behavior data")
    improvement_history: Optional[List[SQLImprovementAttempt]] = Field(None, description="History of SQL improvement attempts")
