import sqlite3

def init_db():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()

    # --- FIX: เพิ่ม factory_sku ในตาราง products ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            sku TEXT NOT NULL,
            factory_sku TEXT NOT NULL, -- เพิ่มคอลัมน์นี้เข้ามา
            details TEXT,
            stock INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            deleted_at TEXT
        )
    ''')

    # --- ตารางอื่นๆ คงเดิม ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            product_details TEXT NOT NULL,
            factory_sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            cost_per_item REAL NOT NULL,
            order_date TEXT NOT NULL,
            updated_at TEXT,
            deleted_at TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INTEGER PRIMARY KEY,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            price_per_item REAL NOT NULL,
            sale_date TEXT NOT NULL,
            updated_at TEXT,
            deleted_at TEXT,
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            updated_at TEXT,
            deleted_at TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(order_id)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database tables updated successfully!")