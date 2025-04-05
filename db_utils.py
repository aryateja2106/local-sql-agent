#!/usr/bin/env python3
"""
Utility functions for database management
"""
import sqlite3
import pandas as pd
import os
import sys
import json
from typing import List, Dict, Any, Optional, Union, Tuple

def connect_to_db(db_path: str) -> Tuple[sqlite3.Connection, sqlite3.Cursor]:
    """Connect to SQLite database and return connection and cursor"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        return conn, cursor
    except sqlite3.Error as e:
        print(f"Error connecting to database: {str(e)}")
        sys.exit(1)

def get_table_info(cursor: sqlite3.Cursor, table_name: str) -> Dict[str, Any]:
    """Get detailed information about a table"""
    table_info = {
        "name": table_name,
        "columns": [],
        "sample_data": [],
        "row_count": 0
    }
    
    # Get column information
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    
    for col in columns:
        col_info = {
            "name": col["name"],
            "type": col["type"],
            "primary_key": bool(col["pk"]),
            "nullable": not bool(col["notnull"]),
            "default": col["dflt_value"]
        }
        table_info["columns"].append(col_info)
    
    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    table_info["row_count"] = cursor.fetchone()[0]
    
    # Get sample data (first 5 rows)
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5;")
    rows = cursor.fetchall()
    
    for row in rows:
        row_data = {}
        for col in table_info["columns"]:
            col_name = col["name"]
            row_data[col_name] = row[col_name]
        table_info["sample_data"].append(row_data)
    
    return table_info

def export_query_to_csv(db_path: str, sql_query: str, output_path: str) -> None:
    """Execute a SQL query and export results to CSV"""
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(sql_query, conn)
        df.to_csv(output_path, index=False)
        print(f"Exported {len(df)} rows to {output_path}")
    except Exception as e:
        print(f"Error exporting to CSV: {str(e)}")
    finally:
        if conn:
            conn.close()

def import_csv_to_table(db_path: str, csv_path: str, table_name: str, if_exists: str = "replace") -> None:
    """Import data from CSV file into a database table"""
    try:
        # Read CSV file
        df = pd.read_csv(csv_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        
        # Import data
        df.to_sql(table_name, conn, if_exists=if_exists, index=False)
        
        print(f"Imported {len(df)} rows from {csv_path} to table {table_name}")
    except Exception as e:
        print(f"Error importing from CSV: {str(e)}")
    finally:
        if conn:
            conn.close()

def export_table_schema(db_path: str, output_path: str) -> None:
    """Export database schema to a JSON file"""
    try:
        conn, cursor = connect_to_db(db_path)
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema = {}
        for table in tables:
            schema[table] = get_table_info(cursor, table)
        
        # Export to JSON file
        with open(output_path, 'w') as f:
            json.dump(schema, f, indent=2)
        
        print(f"Exported schema to {output_path}")
    except Exception as e:
        print(f"Error exporting schema: {str(e)}")
    finally:
        if conn:
            conn.close()

def run_interactive_query(db_path: str) -> None:
    """Run an interactive SQL query session"""
    conn, cursor = connect_to_db(db_path)
    
    print("\nInteractive SQL Query Session")
    print("Type 'exit' or 'quit' to end the session")
    print("Type 'tables' to list all tables")
    print("Type 'schema <table_name>' to see table schema")
    
    while True:
        query = input("\nSQL> ").strip()
        
        if query.lower() in ('exit', 'quit'):
            break
        
        if query.lower() == 'tables':
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]
            print("\nAvailable tables:")
            for table in tables:
                print(f"- {table}")
            continue
        
        if query.lower().startswith('schema '):
            table_name = query[7:].strip()
            try:
                table_info = get_table_info(cursor, table_name)
                print(f"\nTable: {table_name} ({table_info['row_count']} rows)")
                print("\nColumns:")
                for col in table_info['columns']:
                    pk = " PRIMARY KEY" if col['primary_key'] else ""
                    null = " NOT NULL" if not col['nullable'] else ""
                    default = f" DEFAULT {col['default']}" if col['default'] else ""
                    print(f"- {col['name']} ({col['type']}){pk}{null}{default}")
                
                print("\nSample data:")
                if table_info['sample_data']:
                    df = pd.DataFrame(table_info['sample_data'])
                    print(df.to_string())
                else:
                    print("No data available")
            except Exception as e:
                print(f"Error retrieving schema: {str(e)}")
            continue
        
        try:
            cursor.execute(query)
            
            if query.lower().strip().startswith(('select', 'with')):
                # For SELECT queries, fetch and display results
                rows = cursor.fetchall()
                if not rows:
                    print("Query returned no results")
                    continue
                
                # Get column names
                columns = [desc[0] for desc in cursor.description]
                
                # Convert to DataFrame for nice display
                df = pd.DataFrame([dict(row) for row in rows])
                print(f"\nResults ({len(rows)} rows):")
                print(df.to_string())
                
                # Ask if user wants to export results
                export = input("\nExport results to CSV? (y/n): ").lower()
                if export == 'y':
                    output_path = input("Enter output CSV path: ")
                    df.to_csv(output_path, index=False)
                    print(f"Exported to {output_path}")
            else:
                # For non-SELECT queries, show affected rows
                print(f"Query executed successfully. Rows affected: {cursor.rowcount}")
                conn.commit()
        
        except Exception as e:
            print(f"Error executing query: {str(e)}")
    
    conn.close()
    print("\nSession ended")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python db_utils.py <command> [options]")
        print("\nCommands:")
        print("  interactive <db_path> - Run an interactive SQL query session")
        print("  export_schema <db_path> <output_json_path> - Export database schema to JSON")
        print("  export_query <db_path> <sql_query> <output_csv_path> - Export query results to CSV")
        print("  import_csv <db_path> <csv_path> <table_name> - Import CSV data to a table")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "interactive" and len(sys.argv) >= 3:
        run_interactive_query(sys.argv[2])
    elif command == "export_schema" and len(sys.argv) >= 4:
        export_table_schema(sys.argv[2], sys.argv[3])
    elif command == "export_query" and len(sys.argv) >= 5:
        export_query_to_csv(sys.argv[2], sys.argv[3], sys.argv[4])
    elif command == "import_csv" and len(sys.argv) >= 5:
        import_csv_to_table(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("Invalid command or missing arguments")
        sys.exit(1)
