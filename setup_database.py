import sqlite3
import random
from datetime import datetime, timedelta

# Connect to SQLite database (will be created if it doesn't exist)
conn = sqlite3.connect('sales_database.db')
cursor = conn.cursor()

# Create tables
cursor.execute('''
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    address TEXT,
    phone TEXT,
    registration_date TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    price REAL NOT NULL,
    stock INTEGER NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    order_date TEXT,
    total_amount REAL,
    status TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    price REAL,
    FOREIGN KEY (order_id) REFERENCES orders (order_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
)
''')

# Sample data
customer_names = [
    "John Smith", "Emma Johnson", "Michael Brown", "Olivia Davis", "James Wilson",
    "Sophia Martinez", "Robert Anderson", "Isabella Thomas", "William Taylor", "Mia Garcia",
    "David Rodriguez", "Emily Hernandez", "Joseph Martinez", "Charlotte Lewis", "Charles Lee",
    "Amelia Walker", "Daniel Hall", "Harper Allen", "Matthew Young", "Abigail King"
]

domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "example.com"]
product_categories = ["Electronics", "Clothing", "Furniture", "Books", "Toys", "Sports", "Home", "Beauty"]
product_prefixes = ["Premium", "Deluxe", "Standard", "Basic", "Professional", "Ultimate", "Essential", "Classic"]
product_types = [
    "Laptop", "Phone", "Tablet", "T-shirt", "Jeans", "Shoes", "Sofa", "Chair", "Table", 
    "Novel", "Textbook", "Doll", "Action Figure", "Ball", "Racket", "Lamp", "Curtains", "Shampoo", "Cream"
]

order_statuses = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]

# Generate dummy data
# Customers
print("Generating customers...")
customers_data = []
for i in range(1, 21):
    name = customer_names[i-1]
    email = name.lower().replace(" ", ".") + "@" + random.choice(domains)
    phone = f"+1-{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
    address = f"{random.randint(100, 999)} {random.choice(['Main', 'Oak', 'Maple', 'Pine', 'Cedar'])} St, {random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix'])}"
    registration_date = (datetime.now() - timedelta(days=random.randint(1, 500))).strftime("%Y-%m-%d")
    
    customers_data.append((i, name, email, address, phone, registration_date))

cursor.executemany("INSERT OR REPLACE INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers_data)

# Products
print("Generating products...")
products_data = []
for i in range(1, 51):
    category = random.choice(product_categories)
    product_type = random.choice(product_types)
    name = f"{random.choice(product_prefixes)} {product_type}"
    price = round(random.uniform(9.99, 999.99), 2)
    stock = random.randint(0, 100)
    
    products_data.append((i, name, category, price, stock))

cursor.executemany("INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?)", products_data)

# Orders and Order Items
print("Generating orders and order items...")
orders_data = []
order_items_data = []

for i in range(1, 101):
    customer_id = random.randint(1, 20)
    order_date = (datetime.now() - timedelta(days=random.randint(1, 365))).strftime("%Y-%m-%d")
    status = random.choice(order_statuses)
    
    # Create order items for this order
    num_items = random.randint(1, 5)
    total_amount = 0
    
    for j in range(num_items):
        order_item_id = (i - 1) * 5 + j + 1
        product_id = random.randint(1, 50)
        quantity = random.randint(1, 3)
        
        # Get product price
        cursor.execute("SELECT price FROM products WHERE product_id = ?", (product_id,))
        price = cursor.fetchone()[0]
        
        item_total = price * quantity
        total_amount += item_total
        
        order_items_data.append((order_item_id, i, product_id, quantity, price))
    
    orders_data.append((i, customer_id, order_date, round(total_amount, 2), status))

cursor.executemany("INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?)", orders_data)
cursor.executemany("INSERT OR REPLACE INTO order_items VALUES (?, ?, ?, ?, ?)", order_items_data)

# Commit and close
conn.commit()

# Verify data
print("Verifying data...")
cursor.execute("SELECT COUNT(*) FROM customers")
print(f"Customers: {cursor.fetchone()[0]}")
cursor.execute("SELECT COUNT(*) FROM products")
print(f"Products: {cursor.fetchone()[0]}")
cursor.execute("SELECT COUNT(*) FROM orders")
print(f"Orders: {cursor.fetchone()[0]}")
cursor.execute("SELECT COUNT(*) FROM order_items")
print(f"Order Items: {cursor.fetchone()[0]}")

conn.close()
print("Database setup complete!")
