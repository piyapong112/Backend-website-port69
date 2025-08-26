from flask import Flask, render_template, request, redirect, url_for, jsonify, flash # เพิ่ม flash เข้ามา
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_here' # เพิ่มบรรทัดนี้

def get_db_connection():
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

# ====================================================================
# NEW DASHBOARD & CHART API
# (นำโค้ดทั้งหมดนี้ไปวางแทนที่ฟังก์ชัน dashboard เดิม)
# ====================================================================

@app.route('/')
def dashboard():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL').fetchall()
    sales = conn.execute('SELECT * FROM sales WHERE deleted_at IS NULL').fetchall()
    products = conn.execute('SELECT * FROM products WHERE deleted_at IS NULL').fetchall()

    # สร้าง Cost Map จาก orders เหมือนเดิม
    cost_map = {o['factory_sku']: o['cost_per_item'] for o in orders}

    total_revenue = 0
    total_cost_of_goods_sold = 0
    total_items_sold = 0

    for sale in sales:
        total_revenue += sale['quantity'] * sale['price_per_item']
        total_items_sold += sale['quantity']
        
        # FIX: ใช้ factory_sku ที่เชื่อมกันโดยตรง ไม่ต้องเดาจาก sku
        product_info = conn.execute('SELECT factory_sku FROM products WHERE product_id = ?', (sale['product_id'],)).fetchone()
        if product_info:
            factory_sku = product_info['factory_sku']
            cost_per_item = cost_map.get(factory_sku, 0)
            total_cost_of_goods_sold += cost_per_item * sale['quantity']

    net_profit = total_revenue - total_cost_of_goods_sold
    net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    current_stock_value = 0
    for product in products:
        cost_per_item = cost_map.get(product['factory_sku'], 0)
        current_stock_value += cost_per_item * product['stock']

    product_profit = {}
    for sale in sales:
        product_info = conn.execute('SELECT name, details, factory_sku FROM products WHERE product_id = ?', (sale['product_id'],)).fetchone()
        if product_info:
            factory_sku = product_info['factory_sku']
            cost_per_item = cost_map.get(factory_sku, 0)
            profit = (sale['price_per_item'] - cost_per_item) * sale['quantity']
            product_key = f"{product_info['name']} ({product_info['details']})"
            product_profit[product_key] = product_profit.get(product_key, 0) + profit
            
    top_profitable_products = sorted(product_profit.items(), key=lambda item: item[1], reverse=True)[:5]
    
    low_stock_products = conn.execute('SELECT * FROM products WHERE stock <= 10 AND deleted_at IS NULL').fetchall()

    total_order_costs = sum(o['quantity'] * o['cost_per_item'] for o in orders)
    payments = conn.execute('SELECT * FROM payments WHERE deleted_at IS NULL').fetchall()
    total_payments = sum(p['amount'] for p in payments)
    total_outstanding = total_order_costs - total_payments

    conn.close()

    return render_template('dashboard.html',
                           net_profit=net_profit,
                           total_revenue=total_revenue,
                           total_cost_of_goods_sold=total_cost_of_goods_sold,
                           net_profit_margin=net_profit_margin,
                           total_items_sold=total_items_sold,
                           current_stock_value=current_stock_value,
                           top_profitable_products=top_profitable_products,
                           low_stock_products=low_stock_products,
                           total_outstanding=total_outstanding)

@app.route('/api/performance_data')
def performance_data():
    conn = get_db_connection()
    sales = conn.execute('SELECT sale_date, quantity, price_per_item, product_id FROM sales WHERE deleted_at IS NULL ORDER BY sale_date ASC').fetchall()
    orders = conn.execute('SELECT factory_sku, cost_per_item FROM orders WHERE deleted_at IS NULL').fetchall()
    cost_map = {o['factory_sku']: o['cost_per_item'] for o in orders}

    daily_data = {}

    for sale in sales:
        day = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
        
        if day not in daily_data:
            daily_data[day] = {'revenue': 0, 'cost': 0, 'profit': 0}
            
        revenue = sale['quantity'] * sale['price_per_item']
        
        # FIX: ใช้ factory_sku ที่เชื่อมกันโดยตรง
        product_info = conn.execute('SELECT factory_sku FROM products WHERE product_id = ?', (sale['product_id'],)).fetchone()
        cost = 0
        if product_info:
            factory_sku = product_info['factory_sku']
            cost_per_item = cost_map.get(factory_sku, 0)
            cost = cost_per_item * sale['quantity']
        
        daily_data[day]['revenue'] += revenue
        daily_data[day]['cost'] += cost
        daily_data[day]['profit'] += (revenue - cost)
        
    conn.close()

    sorted_days = sorted(daily_data.keys())
    chart_data = {
        'labels': sorted_days,
        'datasets': [
            {'label': 'ยอดขาย', 'data': [daily_data[day]['revenue'] for day in sorted_days], 'borderColor': 'rgba(75, 192, 192, 1)', 'tension': 0.1},
            {'label': 'ต้นทุน', 'data': [daily_data[day]['cost'] for day in sorted_days], 'borderColor': 'rgba(255, 99, 132, 1)', 'tension': 0.1},
            {'label': 'กำไร', 'data': [daily_data[day]['profit'] for day in sorted_days], 'borderColor': 'rgba(54, 162, 235, 1)', 'tension': 0.1}
        ]
    }
    return jsonify(chart_data)
@app.route('/accounting')
def accounting_page():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL ORDER BY order_date DESC').fetchall()
    payments = conn.execute('SELECT * FROM payments WHERE deleted_at IS NULL').fetchall()
    
    # สร้าง dictionary เพื่อเก็บยอดชำระของแต่ละ order_id
    payments_map = {}
    for payment in payments:
        order_id = payment['order_id']
        if order_id not in payments_map:
            payments_map[order_id] = 0
        payments_map[order_id] += payment['amount']

    # เตรียมข้อมูลสำหรับส่งไปที่หน้าเว็บ
    accounting_data = []
    total_order_costs = 0
    total_paid_amount = 0

    for order in orders:
        order_id = order['order_id']
        total_cost = order['quantity'] * order['cost_per_item']
        paid_amount = payments_map.get(order_id, 0)
        outstanding = total_cost - paid_amount

        accounting_data.append({
            'order_id': order_id,
            'product_details': order['product_details'],
            'factory_sku': order['factory_sku'],
            'order_date': order['order_date'],
            'total_cost': total_cost,
            'paid_amount': paid_amount,
            'outstanding': outstanding
        })
        total_order_costs += total_cost
        total_paid_amount += paid_amount

    total_outstanding = total_order_costs - total_paid_amount

    conn.close()
    
    return render_template('accounting.html', 
                           accounting_data=accounting_data,
                           total_order_costs=total_order_costs,
                           total_paid_amount=total_paid_amount,
                           total_outstanding=total_outstanding)


@app.route('/forms/stock-in')
def forms_stock_in():
    return render_template('stock_in_forms.html')

@app.route('/forms/stock-out')
def forms_stock_out():
    return render_template('stock_out_forms.html')

@app.route('/forms/payments')
def forms_payments():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL').fetchall()
    conn.close()
    return render_template('payments_forms.html', orders=orders)

@app.route('/api/products')
def api_products():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products WHERE deleted_at IS NULL').fetchall()
    conn.close()
    return jsonify([dict(row) for row in products])

@app.route('/api/orders')
def api_orders():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL').fetchall()
    conn.close()
    return jsonify([dict(row) for row in orders])

@app.route('/submit_order', methods=['POST'])
def submit_order():
    if request.method == 'POST':
        product_details_list = request.form.getlist('product_details[]')
        factory_sku_list = request.form.getlist('factory_sku[]')
        quantity_list = request.form.getlist('quantity[]')
        cost_per_item_list = request.form.getlist('cost_per_item[]')

        conn = get_db_connection()
        for product_details, factory_sku, quantity, cost_per_item in zip(product_details_list, factory_sku_list, quantity_list, cost_per_item_list):
            if product_details and factory_sku and quantity and cost_per_item:
                conn.execute('INSERT INTO orders (product_details, factory_sku, quantity, cost_per_item, order_date) VALUES (?, ?, ?, ?, ?)',
                             (product_details, factory_sku, int(quantity), float(cost_per_item), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        flash('คุณได้บันทึกข้อมูล "สั่งซื้อ" เรียบร้อยแล้ว!') # เพิ่มข้อความ Flash
        return redirect(url_for('forms_stock_in')) # กลับไปที่หน้าฟอร์มเดิม

@app.route('/submit_stock_in', methods=['POST'])
def submit_stock_in():
    if request.method == 'POST':
        product_name_list = request.form.getlist('product_name[]')
        sku_list = request.form.getlist('sku[]')
        factory_sku_list = request.form.getlist('factory_sku[]') # รับข้อมูลใหม่
        details_list = request.form.getlist('details[]')
        quantity_list = request.form.getlist('quantity[]')
        group_index_list = request.form.getlist('group_index[]')
        
        conn = get_db_connection()
        for main_index, (product_name, sku, factory_sku) in enumerate(zip(product_name_list, sku_list, factory_sku_list)):
            for i, details in enumerate(details_list):
                if i < len(group_index_list) and int(group_index_list[i]) == main_index:
                    quantity = quantity_list[i]
                    if product_name and sku and factory_sku and details and quantity:
                        quantity_int = int(quantity)
                        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        existing_product = conn.execute('SELECT * FROM products WHERE sku = ? AND details = ?', (sku, details)).fetchone()
                        if existing_product:
                            conn.execute('UPDATE products SET stock = stock + ? WHERE sku = ? AND details = ?', (quantity_int, sku, details))
                        else:
                            # เพิ่ม factory_sku ตอน INSERT
                            conn.execute('INSERT INTO products (name, sku, factory_sku, details, stock, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                                         (product_name, sku, factory_sku, details, quantity_int, created_at))
        conn.commit()
        conn.close()
        flash('คุณได้บันทึกข้อมูล "รับของ" เรียบร้อยแล้ว!') # เพิ่มข้อความ Flash
        return redirect(url_for('forms_stock_in')) # กลับไปที่หน้าฟอร์มเดิม

@app.route('/submit_stock_out', methods=['POST'])
def submit_stock_out():
    if request.method == 'POST':
        sku_list = request.form.getlist('sku[]')
        details_list = request.form.getlist('details[]')
        quantity_list = request.form.getlist('quantity[]')
        price_list = request.form.getlist('price[]')
        group_index_list = request.form.getlist('group_index[]')

        conn = get_db_connection()
        for main_index, sku in enumerate(sku_list):
            for i, details in enumerate(details_list):
                if i < len(group_index_list) and int(group_index_list[i]) == main_index:
                    quantity = quantity_list[i]
                    price = price_list[i]
                    if details and quantity and price:
                        quantity_int = int(quantity)
                        price_float = float(price)
                        sale_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        product = conn.execute('SELECT product_id FROM products WHERE sku = ? AND details = ?', (sku, details)).fetchone()
                        if product:
                            product_id = product['product_id']
                            conn.execute('INSERT INTO sales (product_id, quantity, price_per_item, sale_date) VALUES (?, ?, ?, ?)',
                                         (product_id, quantity_int, price_float, sale_date))
                            conn.execute('UPDATE products SET stock = stock - ? WHERE product_id = ?', (quantity_int, product_id))
        conn.commit()
        conn.close()
        flash('คุณได้บันทึกข้อมูล "ขายออก" เรียบร้อยแล้ว!') # เพิ่มข้อความ Flash
        return redirect(url_for('forms_stock_out')) # กลับไปที่หน้าฟอร์มเดิม

@app.route('/submit_payment', methods=['POST'])
def submit_payment():
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        amount = request.form.get('amount')
        payment_date = request.form.get('payment_date') # รับวันที่จากฟอร์ม
        
        # ถ้าไม่ได้กรอกวันที่ ให้ใช้วันที่ปัจจุบัน
        if not payment_date:
            payment_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        conn.execute('INSERT INTO payments (order_id, amount, payment_date) VALUES (?, ?, ?)',
                     (order_id, float(amount), payment_date))
        conn.commit()
        conn.close()
        flash('บันทึกการชำระเงินเรียบร้อยแล้ว!')
        return redirect(url_for('accounting_page'))
    
@app.route('/data')
def data_management():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL ORDER BY order_id DESC').fetchall()
    products = conn.execute('SELECT * FROM products WHERE deleted_at IS NULL ORDER BY product_id DESC').fetchall()
    sales_with_details = conn.execute('''
        SELECT s.sale_id, p.sku, p.details, s.quantity, s.price_per_item, s.sale_date, s.updated_at
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        WHERE s.deleted_at IS NULL
        ORDER BY s.sale_id DESC
    ''').fetchall()
    conn.close()
    return render_template('data_management.html',
                           orders=orders, products=products, sales_with_details=sales_with_details)

@app.route('/delete/<item_type>/<int:item_id>')
def soft_delete(item_type, item_id):
    conn = get_db_connection()
    delete_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if item_type == 'order':
        conn.execute('UPDATE orders SET deleted_at = ? WHERE order_id = ?', (delete_time, item_id))
    elif item_type == 'product':
        conn.execute('UPDATE products SET deleted_at = ? WHERE product_id = ?', (delete_time, item_id))
    elif item_type == 'sale':
        conn.execute('UPDATE sales SET deleted_at = ? WHERE sale_id = ?', (delete_time, item_id))
    conn.commit()
    conn.close()
    return redirect(url_for('data_management'))

@app.route('/trash')
def trash_bin():
    conn = get_db_connection()
    three_days_ago = datetime.now() - timedelta(days=3)
    deleted_orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NOT NULL AND deleted_at >= ?', (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'),)).fetchall()
    deleted_products = conn.execute('SELECT * FROM products WHERE deleted_at IS NOT NULL AND deleted_at >= ?', (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'),)).fetchall()
    deleted_sales = conn.execute('SELECT * FROM sales WHERE deleted_at IS NOT NULL AND deleted_at >= ?', (three_days_ago.strftime('%Y-%m-%d %H:%M:%S'),)).fetchall()
    conn.close()
    return render_template('trash.html', orders=deleted_orders, products=deleted_products, sales=deleted_sales)

@app.route('/restore/<item_type>/<int:item_id>')
def restore_item(item_type, item_id):
    conn = get_db_connection()
    if item_type == 'order':
        conn.execute('UPDATE orders SET deleted_at = NULL WHERE order_id = ?', (item_id,))
    elif item_type == 'product':
        conn.execute('UPDATE products SET deleted_at = NULL WHERE product_id = ?', (item_id,))
    elif item_type == 'sale':
        conn.execute('UPDATE sales SET deleted_at = NULL WHERE sale_id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('trash_bin'))

@app.route('/reset_db')
def reset_db():
    db_path = 'inventory.db'
    if os.path.exists(db_path):
        os.remove(db_path)
    import database
    database.init_db()
    return redirect(url_for('dashboard'))

@app.route('/outstanding')
def outstanding_page():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL').fetchall()
    outstanding_items = []
    for order in orders:
        payments_for_order = conn.execute('SELECT SUM(amount) as total_paid FROM payments WHERE order_id = ?', (order['order_id'],)).fetchone()
        total_paid = payments_for_order['total_paid'] if payments_for_order['total_paid'] else 0
        outstanding_amount = (order['quantity'] * order['cost_per_item']) - total_paid
        if outstanding_amount > 0:
            outstanding_items.append({'factory_sku': order['factory_sku'], 'amount': outstanding_amount, 'order_id': order['order_id']})
    conn.close()
    return render_template('outstanding.html', outstanding_items=outstanding_items)

@app.route('/edit/order/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    conn = get_db_connection()
    if request.method == 'POST':
        product_details = request.form['product_details']
        factory_sku = request.form['factory_sku']
        quantity = int(request.form['quantity'])
        cost_per_item = float(request.form['cost_per_item'])
        conn.execute('UPDATE orders SET product_details = ?, factory_sku = ?, quantity = ?, cost_per_item = ?, updated_at = ? WHERE order_id = ?',
             (product_details, factory_sku, quantity, cost_per_item, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), order_id))
        conn.commit()
        conn.close()
        return redirect(url_for('data_management'))
    order = conn.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,)).fetchone()
    conn.close()
    return render_template('edit_order.html', order=order)

@app.route('/edit/product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name']
        sku = request.form['sku']
        factory_sku = request.form['factory_sku'] # รับข้อมูลใหม่
        details = request.form['details']
        stock = int(request.form['stock'])
        # เพิ่ม factory_sku ตอน UPDATE
        conn.execute('UPDATE products SET name = ?, sku = ?, factory_sku = ?, details = ?, stock = ?, updated_at = ? WHERE product_id = ?',
             (name, sku, factory_sku, details, stock, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), product_id))
        conn.commit()
        conn.close()
        return redirect(url_for('data_management'))
    product = conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
    conn.close()
    return render_template('edit_product.html', product=product)

@app.route('/edit/sale/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    conn = get_db_connection()
    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])
        price_per_item = float(request.form['price_per_item'])
        conn.execute('UPDATE sales SET product_id = ?, quantity = ?, price_per_item = ?, updated_at = ? WHERE sale_id = ?',
             (product_id, quantity, price_per_item, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sale_id))
        conn.commit()
        conn.close()
        return redirect(url_for('data_management'))
    sale = conn.execute('SELECT * FROM sales WHERE sale_id = ?', (sale_id,)).fetchone()
    products = conn.execute('SELECT * FROM products WHERE deleted_at IS NULL').fetchall()
    conn.close()
    return render_template('edit_sale.html', sale=sale, products=products)

@app.route('/edit/payment/<int:payment_id>', methods=['GET', 'POST'])
def edit_payment(payment_id):
    conn = get_db_connection()
    if request.method == 'POST':
        order_id = int(request.form['order_id'])
        amount = float(request.form['amount'])
        conn.execute('UPDATE payments SET order_id = ?, amount = ? WHERE payment_id = ?',
                     (order_id, amount, payment_id))
        conn.commit()
        conn.close()
        return redirect(url_for('data_management'))
    payment = conn.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,)).fetchone()
    orders = conn.execute('SELECT * FROM orders WHERE deleted_at IS NULL').fetchall()
    conn.close()
    return render_template('edit_payment.html', payment=payment, orders=orders)

# --- ฟังก์ชัน Hard Delete ที่ซ้ำซ้อนและเป็นปัญหา ถูกลบออกไปแล้ว ---

if __name__ == '__main__':
    app.run(debug=True)