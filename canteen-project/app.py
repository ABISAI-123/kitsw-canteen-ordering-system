from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, time
import random
import string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "canteen_secret_key")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# If you later use PostgreSQL, change DATABASE_URL env var
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(BASE_DIR, "canteen.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # 'user' or 'admin'

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    available = db.Column(db.Boolean, default=True)
    # time availability (HH:MM strings)
    available_from = db.Column(db.String(5), nullable=True)  # e.g. "08:00"
    available_to = db.Column(db.String(5), nullable=True)    # e.g. "11:00"

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    pickup_time = db.Column(db.String(30), nullable=False)   # "12:30 PM"
    status = db.Column(db.String(30), default="Pending")     # Pending / Preparing / Ready / Completed / Cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status = db.Column(db.String(20), default="Unpaid")  # Unpaid / Paid / Failed
    token = db.Column(db.String(12), nullable=True)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("menu_item.id"), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------- DB init and sample data -------------
def init_db():
    db.create_all()
    # create default admin if missing
    admin = User.query.filter_by(role="admin").first()
    if not admin:
        admin_user = User(
            username="canteen_admin",
            password_hash=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin_user)
    # sample menu items if none exist
    if MenuItem.query.count() == 0:
        sample = [
            ("Chicken Biryani", 120.0, True, "11:00", "15:00"),
            ("Veg Biryani", 100.0, True, "11:00", "15:00"),
            ("Samosa", 15.0, True, "09:00", "17:00"),
            ("Egg Manchuria", 80.0, True, "11:00", "15:00"),
            ("Chicken Manchuria", 100.0, True, "11:00", "15:00"),
            ("Idli", 30.0, True, "07:00", "10:30"),
            ("Dosa", 40.0, True, "07:00", "11:00"),
            ("Poori", 35.0, True, "07:00", "11:00")
        ]
        for n, p, av, f, t in sample:
            db.session.add(MenuItem(name=n, price=p, available=av, available_from=f, available_to=t))
    db.session.commit()

# ------------- Helpers -------------
def is_logged_in():
    return 'username' in session

def is_admin():
    return session.get('role') == 'admin'

def now_time_str():
    # current time in HH:MM
    return datetime.now().strftime("%H:%M")

def in_availability(item: MenuItem):
    if not item.available:
        return False
    if item.available_from and item.available_to:
        cur = datetime.now().time()
        fr = datetime.strptime(item.available_from, "%H:%M").time()
        to = datetime.strptime(item.available_to, "%H:%M").time()
        if fr <= cur <= to:
            return True
        return False
    return True

def gen_token(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

# ------------- Routes -------------
@app.route('/')
def root():
    if is_logged_in():
        if is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

# ---------- Auth ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']
        if not uname or not pwd:
            flash("Please provide valid username and password", "danger")
            return redirect(url_for('register'))
        if User.query.filter_by(username=uname).first():
            flash("Username already exists", "danger")
            return redirect(url_for('register'))
        user = User(username=uname, password_hash=generate_password_hash(pwd), role='user')
        db.session.add(user)
        db.session.commit()
        flash("Registered! Please login.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username'].strip()
        pwd = request.form['password']
        user = User.query.filter_by(username=uname).first()
        if user and check_password_hash(user.password_hash, pwd):
            session['username'] = user.username
            session['role'] = user.role
            flash("Login successful", "success")
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('student_dashboard'))
        flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- Student ----------
@app.route('/student/dashboard')
def student_dashboard():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    return render_template('student_dashboard.html')

@app.route('/menu')
def menu():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    items = MenuItem.query.order_by(MenuItem.name).all()
    # compute current availability and average rating
    item_data = []
    for it in items:
        avg = None
        ratings = Feedback.query.filter_by(item_id=it.id).all()
        if ratings:
            avg = round(sum(r.rating for r in ratings) / len(ratings), 2)
        item_data.append({
            'item': it,
            'available_now': in_availability(it),
            'avg_rating': avg
        })
    return render_template('menu.html', items=item_data)

@app.route('/order/<int:item_id>', methods=['GET', 'POST'])
def order_form(item_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    item = MenuItem.query.get_or_404(item_id)
    if request.method == 'POST':
        # check availability by time and boolean
        if not in_availability(item):
            flash("This item is not available at the selected time.", "danger")
            return redirect(url_for('menu'))
        time_val = request.form.get('order_time', '').strip()
        ampm = request.form.get('order_ampm', '').strip()
        if not time_val or ampm not in ['AM', 'PM']:
            flash("Please enter valid time and AM/PM", "danger")
            return redirect(url_for('order_form', item_id=item_id))
        pickup = f"{time_val} {ampm}"
        new_order = Order(
            username=session['username'],
            item_name=item.name,
            total_price=item.price,
            pickup_time=pickup,
            status="Pending",
            token=gen_token(6)
        )
        db.session.add(new_order)
        db.session.commit()
        # redirect to payment page (dummy)
        return redirect(url_for('payment', order_id=new_order.id))
    return render_template('order.html', item=item)

@app.route('/payment/<int:order_id>', methods=['GET', 'POST'])
def payment(order_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    order = Order.query.get_or_404(order_id)
    if order.username != session['username'] and not is_admin():
        flash("Not authorized", "danger")
        return redirect(url_for('student_dashboard'))
    if request.method == 'POST':
        method = request.form.get('method')
        # Fake a small processing delay omitted; mark Paid
        order.payment_status = "Paid"
        db.session.commit()
        flash(f"Payment successful via {method} (dummy).", "success")
        return redirect(url_for('order_receipt', order_id=order.id))
    return render_template('payment.html', amount=order.total_price, order=order)

@app.route('/order/receipt/<int:order_id>')
def order_receipt(order_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    order = Order.query.get_or_404(order_id)
    # only allow owner or admin
    if not is_admin() and order.username != session['username']:
        flash("Not authorized", "danger")
        return redirect(url_for('student_dashboard'))
    return render_template('order_receipt.html', order=order)

@app.route('/order/history')
def order_history():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    orders = Order.query.filter_by(username=session['username']).order_by(Order.created_at.desc()).all()
    total_spent = sum(o.total_price for o in orders if o.payment_status == "Paid")
    return render_template('order_history.html', orders=orders, total_spent=total_spent)

@app.route('/order/cancel/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    o = Order.query.get_or_404(order_id)
    if o.username != session['username']:
        return jsonify({"error": "Not authorized"}), 403
    if o.status != "Pending":
        return jsonify({"error": "Only pending orders can be cancelled"}), 400
    o.status = "Cancelled"
    db.session.commit()
    return jsonify({"ok": True})

# ---------- Admin ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

@app.route('/admin/menu', methods=['GET', 'POST'])
def admin_menu():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        af = request.form.get('available_from', '').strip() or None
        at = request.form.get('available_to', '').strip() or None
        if not name or not price:
            flash("Provide name and price", "danger")
            return redirect(url_for('admin_menu'))
        try:
            price_val = float(price)
        except:
            flash("Price must be a number", "danger")
            return redirect(url_for('admin_menu'))
        item = MenuItem(name=name, price=price_val, available=True, available_from=af, available_to=at)
        db.session.add(item)
        db.session.commit()
        flash("Item added", "success")
        return redirect(url_for('admin_menu'))
    items = MenuItem.query.order_by(MenuItem.name).all()
    return render_template('admin_menu.html', items=items)

@app.route('/admin/menu/toggle/<int:item_id>')
def admin_toggle_menu(item_id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    it = MenuItem.query.get_or_404(item_id)
    it.available = not it.available
    db.session.commit()
    return redirect(url_for('admin_menu'))

@app.route('/admin/orders', methods=['GET', 'POST'])
def admin_orders():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))

    # Allow filtering by status
    status = request.args.get('status', None)

    try:
        if status:
            orders = Order.query.filter_by(status=status).order_by(Order.created_at.desc()).all()
        else:
            orders = Order.query.order_by(Order.created_at.desc()).all()
    except Exception as e:
        flash("Error fetching orders: " + str(e), "danger")
        orders = []

    return render_template('admin_orders.html', orders=orders, filter_status=status)


@app.route('/admin/orders/update', methods=['POST'])
def admin_update_order():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))

    oid = request.form.get('order_id')
    new_status = request.form.get('status')

    if oid and new_status:
        try:
            oid = int(oid)
            order = Order.query.get(oid)
            if order:
                order.status = new_status
                db.session.commit()
                flash("Order status updated successfully", "success")
            else:
                flash("Order not found", "warning")
        except Exception as e:
            db.session.rollback()
            flash("Failed to update order: " + str(e), "danger")

    return redirect(url_for('admin_orders'))


# ---------- Feedback ----------
@app.route('/feedback/<int:item_id>', methods=['POST'])
def submit_feedback(item_id):
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()
    if rating < 1 or rating > 5:
        flash("Please provide a rating between 1 and 5", "danger")
        return redirect(url_for('menu'))
    fb = Feedback(item_id=item_id, username=session['username'], rating=rating, comment=comment)
    db.session.add(fb)
    db.session.commit()
    flash("Thanks for the feedback!", "success")
    return redirect(url_for('menu'))

# ---------- JSON APIs for polling ----------
@app.route('/api/orders')  # user-specific
def api_orders():
    if not is_logged_in() or is_admin():
        return jsonify({"error": "Not authorized"}), 403
    orders = Order.query.filter_by(username=session['username']).order_by(Order.created_at.desc()).all()
    out = []
    for o in orders:
        out.append({
            "id": o.id,
            "item_name": o.item_name,
            "total_price": o.total_price,
            "pickup_time": o.pickup_time,
            "status": o.status,
            "payment_status": o.payment_status,
            "token": o.token,
            "created_at": o.created_at.isoformat()
        })
    return jsonify(out)

@app.route('/api/admin/orders')
def api_admin_orders():
    if not is_logged_in() or not is_admin():
        return jsonify({"error": "Not authorized"}), 403
    orders = Order.query.order_by(Order.created_at.desc()).all()
    out = []
    for o in orders:
        out.append({
            "id": o.id,
            "username": o.username,
            "item_name": o.item_name,
            "total_price": o.total_price,
            "pickup_time": o.pickup_time,
            "status": o.status,
            "payment_status": o.payment_status,
            "token": o.token,
            "created_at": o.created_at.isoformat()
        })
    return jsonify(out)

# ---------- Utility: create DB and run ----------
if __name__ == '__main__':
    with app.app_context():
        init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

