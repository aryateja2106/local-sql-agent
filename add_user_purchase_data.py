import sqlite3
import random
from datetime import datetime, timedelta

# Connect to SQLite database
conn = sqlite3.connect('sales_database.db')
cursor = conn.cursor()

# Create a new table for user purchase behavior
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_purchase_behavior (
    user_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    has_purchased_product BOOLEAN NOT NULL,
    purchase_likelihood REAL NOT NULL,
    has_purchased_service BOOLEAN NOT NULL,
    service_purchase_likelihood REAL NOT NULL,
    last_interaction_date TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
)
''')

# Get existing customer IDs
cursor.execute("SELECT customer_id FROM customers")
customer_ids = [row[0] for row in cursor.fetchall()]

# Generate 15 rows of user purchase behavior data
purchase_behavior_data = []
for i in range(1, 16):
    customer_id = random.choice(customer_ids)
    has_purchased_product = random.choice([0, 1])  # 0 for False, 1 for True
    
    # Set purchase likelihood - higher if they've already purchased
    purchase_likelihood = random.uniform(0.7, 0.95) if has_purchased_product else random.uniform(0.1, 0.6)
    
    has_purchased_service = random.choice([0, 1])
    service_purchase_likelihood = random.uniform(0.7, 0.95) if has_purchased_service else random.uniform(0.1, 0.6)
    
    # Random date within the last 90 days
    last_interaction_date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
    
    purchase_behavior_data.append((
        i, 
        customer_id, 
        has_purchased_product, 
        purchase_likelihood, 
        has_purchased_service, 
        service_purchase_likelihood, 
        last_interaction_date
    ))

# Insert data into the table
cursor.executemany(
    "INSERT OR REPLACE INTO user_purchase_behavior VALUES (?, ?, ?, ?, ?, ?, ?)", 
    purchase_behavior_data
)

# Commit changes
conn.commit()

# Verify data
cursor.execute("SELECT COUNT(*) FROM user_purchase_behavior")
print(f"User Purchase Behavior Records: {cursor.fetchone()[0]}")

# Show sample data
cursor.execute("""
SELECT 
    upb.user_id, 
    c.name as customer_name, 
    upb.has_purchased_product, 
    upb.purchase_likelihood, 
    upb.has_purchased_service, 
    upb.service_purchase_likelihood, 
    upb.last_interaction_date
FROM user_purchase_behavior upb
JOIN customers c ON upb.customer_id = c.customer_id
LIMIT 5
""")

print("\nSample data:")
rows = cursor.fetchall()
for row in rows:
    print(row)

# Close connection
conn.close()
print("\nUser purchase behavior data added successfully!")
