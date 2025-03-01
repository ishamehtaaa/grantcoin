from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import time
import random
from datetime import datetime
import threading
import decimal

# Set decimal precision to handle extremely small values
decimal.getcontext().prec = 20

app = Flask(__name__)
app.secret_key = 'grantcoin_super_secret_key'  # In a real app, this would be properly secured

# Global flag to control price fluctuation
price_fluctuation_active = False
fluctuation_thread = None

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

# Update coin price
def update_price_in_db(new_price):
    conn = sqlite3.connect('grantcoin.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO coin_price (price, timestamp) VALUES (?, ?)',
                  (new_price, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# Price fluctuation function with nano-precision decimal handling
def random_price_fluctuation():
    global price_fluctuation_active
    
    while price_fluctuation_active:
        try:
            # Get current price
            current_price = decimal.Decimal(str(get_coin_price()))
            
            # For extremely small prices, we need larger percentage changes to see movement
            if current_price < decimal.Decimal('0.000001'):
                # For nano-prices, allow bigger swings (huge volatility is realistic for these tokens)
                percentage_change = decimal.Decimal(str(random.uniform(-15.0, 25.0)))
            else:
                # For higher prices, more moderate changes
                percentage_change = decimal.Decimal(str(random.uniform(-7.5, 9.5)))
            
            # Calculate new price with higher precision
            change_amount = current_price * (percentage_change / decimal.Decimal('100'))
            new_price = max(decimal.Decimal('0.0000000000001'), current_price + change_amount)  # Allow extremely small values
            
            # For tiny prices, keep full precision
            if new_price < decimal.Decimal('0.000001'):
                # For nano prices, don't round, keep full precision
                pass
            elif new_price < decimal.Decimal('0.001'):
                # For micro prices, use 10-12 decimal places
                decimal_places = random.randint(10, 12)
                new_price = decimal.Decimal(f"{new_price:.{decimal_places}f}")
            else:
                # For larger prices, use fewer decimal places
                decimal_places = random.randint(3, 8)
                new_price = decimal.Decimal(f"{new_price:.{decimal_places}f}")
            
            # Update price in database
            update_price_in_db(float(new_price))
            
            # Determine the best format for displaying the price in the log
            if current_price < decimal.Decimal('0.000001'):
                print(f"Price updated: ${float(current_price):.12f} → ${float(new_price):.12f} ({float(percentage_change):+.2f}%)")
            else:
                print(f"Price updated: ${float(current_price):.6f} → ${float(new_price):.6f} ({float(percentage_change):+.2f}%)")
            
            # Sleep for 5 minutes
            for _ in range(30):  # Check every 10 seconds if we should stop
                if not price_fluctuation_active:
                    break
                time.sleep(10)
                
        except Exception as e:
            print(f"Error in price fluctuation thread: {str(e)}")
            time.sleep(30)  # Wait a bit before retrying

# Generate a random starting price in a realistic range for new cryptocurrencies
def generate_random_price():
    # Many new tokens start in these ranges
    price_tier = random.randint(1, 5)
    
    if price_tier == 1:  # "Nano" price tier (e.g., $0.000000000001 to $0.000000999999)
        # Use scientific notation for extremely small values to avoid floating point issues
        power = random.randint(-12, -7)
        mantissa = random.uniform(1, 999)
        return mantissa * (10 ** power)
    elif price_tier == 2:  # "Micro" price tier (e.g., $0.000001 to $0.000999)
        power = random.randint(-6, -4)
        mantissa = random.uniform(1, 999)
        return mantissa * (10 ** power)
    elif price_tier == 3:  # "Mini" price tier (e.g., $0.001 to $0.009)
        return round(random.uniform(0.001, 0.009), random.randint(6, 10))
    elif price_tier == 4:  # "Low" price tier (e.g., $0.01 to $0.99)
        return round(random.uniform(0.01, 0.99), random.randint(3, 5))
    else:  # "Medium" price tier (e.g., $1.00 to $10.00)
        return round(random.uniform(1.0, 10.0), random.randint(2, 4))

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
    
    # Get historical prices for a simple chart
    cursor.execute('''
    SELECT price, timestamp FROM coin_price
    ORDER BY timestamp DESC LIMIT 20
    ''')
    price_history = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                           user=user, 
                           transactions=transactions, 
                           price=price,
                           price_history=price_history)

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
    
    # Calculate coins to buy with higher precision
    coin_amount = decimal.Decimal(str(amount)) / decimal.Decimal(str(price))
    # Round to 8 decimal places for coin amount (like Bitcoin)
    coin_amount = float(round(coin_amount, 8))
    
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
        flash(f'Successfully bought {coin_amount:.8f} GrantCoins!')
    
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
    
    # Calculate amount to receive with higher precision
    amount = decimal.Decimal(str(coin_amount)) * decimal.Decimal(str(price))
    amount = float(round(amount, 2))  # Round to 2 decimal places for currency
    
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
        flash(f'Successfully sold {coin_amount:.8f} GrantCoins!')
    
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
    cursor.execute('SELECT * FROM coin_price ORDER BY id DESC LIMIT 20')
    price_history = cursor.fetchall()
    
    # Get recent transactions
    cursor.execute('''
    SELECT t.*, u.username 
    FROM transactions t 
    JOIN users u ON t.user_id = u.id 
    ORDER BY t.timestamp DESC LIMIT 20
    ''')
    transactions = cursor.fetchall()
    
    # Check price fluctuation status
    global price_fluctuation_active
    
    conn.close()
    
    return render_template('admin.html', 
                           users=users, 
                           price=price, 
                           price_history=price_history,
                           transactions=transactions,
                           price_fluctuation_active=price_fluctuation_active)

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
        
        flash(f'Price updated to ${new_price:.5f}!')
    
    return redirect(url_for('admin'))

@app.route('/toggle_price_fluctuation', methods=['POST'])
def toggle_price_fluctuation():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    global price_fluctuation_active, fluctuation_thread
    
    # Toggle the state
    price_fluctuation_active = not price_fluctuation_active
    
    if price_fluctuation_active:
        # Start the fluctuation thread
        fluctuation_thread = threading.Thread(target=random_price_fluctuation)
        fluctuation_thread.daemon = True  # Thread will end when main program ends
        fluctuation_thread.start()
        flash('Automatic price fluctuation started! Prices will change every 5 minutes.')
    else:
        # Thread will stop on its own due to the global flag
        flash('Automatic price fluctuation stopped.')
    
    return redirect(url_for('admin'))

@app.route('/generate_new_price', methods=['POST'])
def generate_new_price():
    """Generate a new random price in a realistic range for new cryptocurrencies"""
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    # Generate a random price with varying decimal precision
    new_price = generate_random_price()
    
    conn = sqlite3.connect('grantcoin.db')
    cursor = conn.cursor()
    
    # Insert new price
    cursor.execute('''
    INSERT INTO coin_price (price, timestamp) 
    VALUES (?, ?)
    ''', (new_price, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    flash(f'Generated new random price: ${new_price:.8f}!')
    return redirect(url_for('admin'))

@app.route('/update_all_balances', methods=['POST'])
def update_all_balances():
    """Update all non-admin user balances to a specified amount"""
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    new_balance = float(request.form['new_balance'])
    
    if new_balance < 0:
        flash('Balance must be non-negative!')
    else:
        conn = sqlite3.connect('grantcoin.db')
        cursor = conn.cursor()
        
        # Update all non-admin users' balances
        cursor.execute('''
        UPDATE users 
        SET balance = ?
        WHERE is_admin = 0
        ''', (new_balance,))
        
        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        flash(f'Updated balance to ${new_balance:.2f} for {affected_rows} users!')
    
    return redirect(url_for('admin'))

@app.route('/update_all_coins', methods=['POST'])
def update_all_coins():
    """Update all non-admin users' coin holdings to a specified amount"""
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    new_coin_amount = float(request.form['new_coin_amount'])
    
    if new_coin_amount < 0:
        flash('Coin amount must be non-negative!')
    else:
        conn = sqlite3.connect('grantcoin.db')
        cursor = conn.cursor()
        
        # Update all non-admin users' coin amounts
        cursor.execute('''
        UPDATE users 
        SET coins = ?
        WHERE is_admin = 0
        ''', (new_coin_amount,))
        
        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        flash(f'Updated coin holdings to {new_coin_amount:.8f} coins for {affected_rows} users!')
    
    return redirect(url_for('admin'))

@app.route('/get_current_price', methods=['GET'])
def get_current_price_api():
    """API endpoint to get the current price for live updates"""
    price = get_coin_price()
    return jsonify({'price': price})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)