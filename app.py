from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'grantcoin_super_secret_key'  # In a real app, this would be properly secured

# Initialize the database
def init_db():
    conn = sqlite3.connect('grantcoin.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        is_admin INTEGER DEFAULT 0,
        balance REAL DEFAULT 1000.00,
        coins REAL DEFAULT 0
    )
    ''')
    
    # Create transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        coin_amount REAL NOT NULL,
        price REAL NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create coin_price table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS coin_price (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price REAL NOT NULL,
        timestamp TEXT NOT NULL
    )
    ''')
    
    # Insert initial coin price if not exists
    cursor.execute('SELECT COUNT(*) FROM coin_price')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO coin_price (price, timestamp) VALUES (?, ?)', 
                      (10.0, datetime.now().isoformat()))
    
    # Create admin user if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO users (username, is_admin) VALUES (?, ?)', 
                      ('admin', 1))
    
    conn.commit()
    conn.close()

# Get current coin price
def get_coin_price():
    conn = sqlite3.connect('grantcoin.db')
    cursor = conn.cursor()
    cursor.execute('SELECT price FROM coin_price ORDER BY id DESC LIMIT 1')
    price = cursor.fetchone()[0]
    conn.close()
    return price

# Routes
@app.route('/')
def index():
    price = get_coin_price()
    return render_template('index.html', price=price)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        
        # Check if username already exists
        conn = sqlite3.connect('grantcoin.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        if user:
            conn.close()
            flash('Username already exists!')
            return redirect(url_for('register'))
        
        # Create new user
        cursor.execute('INSERT INTO users (username) VALUES (?)', (username,))
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        
        conn = sqlite3.connect('grantcoin.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            conn.close()
            
            if user['is_admin']:
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('dashboard'))
        else:
            conn.close()
            flash('User not found!')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('grantcoin.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get user data
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    # Get transaction history
    cursor.execute('''
    SELECT * FROM transactions 
    WHERE user_id = ? 
    ORDER BY timestamp DESC LIMIT 10
    ''', (session['user_id'],))
    transactions = cursor.fetchall()
    
    # Get current price
    price = get_coin_price()
    
    conn.close()
    
    return render_template('dashboard.html', 
                           user=user, 
                           transactions=transactions, 
                           price=price)

@app.route('/buy', methods=['POST'])
def buy():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    amount = float(request.form['amount'])
    
    conn = sqlite3.connect('grantcoin.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get user data
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    # Get current price
    price = get_coin_price()
    
    # Calculate coins to buy
    coin_amount = amount / price
    
    if amount <= 0:
        flash('Please enter a positive amount!')
    elif user['balance'] < amount:
        flash('Insufficient balance!')
    else:
        # Update user balance and coins
        cursor.execute('''
        UPDATE users 
        SET balance = balance - ?, coins = coins + ? 
        WHERE id = ?
        ''', (amount, coin_amount, session['user_id']))
        
        # Record transaction
        cursor.execute('''
        INSERT INTO transactions (user_id, type, amount, coin_amount, price, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], 'buy', amount, coin_amount, price, datetime.now().isoformat()))
        
        conn.commit()
        flash(f'Successfully bought {coin_amount:.4f} GrantCoins!')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/sell', methods=['POST'])
def sell():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    coin_amount = float(request.form['coin_amount'])
    
    conn = sqlite3.connect('grantcoin.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get user data
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    # Get current price
    price = get_coin_price()
    
    # Calculate amount to receive
    amount = coin_amount * price
    
    if coin_amount <= 0:
        flash('Please enter a positive amount!')
    elif user['coins'] < coin_amount:
        flash('Insufficient coins!')
    else:
        # Update user balance and coins
        cursor.execute('''
        UPDATE users 
        SET balance = balance + ?, coins = coins - ? 
        WHERE id = ?
        ''', (amount, coin_amount, session['user_id']))
        
        # Record transaction
        cursor.execute('''
        INSERT INTO transactions (user_id, type, amount, coin_amount, price, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], 'sell', amount, coin_amount, price, datetime.now().isoformat()))
        
        conn.commit()
        flash(f'Successfully sold {coin_amount:.4f} GrantCoins!')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/admin')
def admin():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('grantcoin.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all users
    cursor.execute('SELECT * FROM users WHERE is_admin = 0')
    users = cursor.fetchall()
    
    # Get current price
    price = get_coin_price()
    
    # Get recent price changes
    cursor.execute('SELECT * FROM coin_price ORDER BY id DESC LIMIT 10')
    price_history = cursor.fetchall()
    
    # Get recent transactions
    cursor.execute('''
    SELECT t.*, u.username 
    FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    ORDER BY t.timestamp DESC LIMIT 20
    ''')
    transactions = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                           users=users, 
                           price=price, 
                           price_history=price_history,
                           transactions=transactions)

@app.route('/update_price', methods=['POST'])
def update_price():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    new_price = float(request.form['new_price'])
    
    if new_price <= 0:
        flash('Price must be positive!')
    else:
        conn = sqlite3.connect('grantcoin.db')
        cursor = conn.cursor()
        
        # Insert new price
        cursor.execute('''
        INSERT INTO coin_price (price, timestamp) 
        VALUES (?, ?)
        ''', (new_price, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        flash(f'Price updated to ${new_price:.2f}!')
    
    return redirect(url_for('admin'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
