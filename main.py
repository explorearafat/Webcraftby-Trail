from flask import Flask, render_template_string, request, redirect, jsonify, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import sqlite3, uuid, datetime, json, time, random, os, zipfile, io
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)
app.secret_key = "secret-key-12345"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['WEBSITE_FOLDER'] = 'static/websites'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

DB = "database.db"
ADMIN_EMAIL = "metabolism@gmail.com"
ADMIN_PASS = "@#$5567"

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['WEBSITE_FOLDER'], exist_ok=True)

# ---------------- DATABASE ----------------
def db():
    return sqlite3.connect(DB)

def init_db():
    con = db()
    cur = con.cursor()

    # Create users table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT UNIQUE,
        fullname TEXT,
        email TEXT UNIQUE,
        whatsapp TEXT,
        gender TEXT,
        dob TEXT,
        profession TEXT,
        password TEXT,
        role TEXT DEFAULT 'user',
        created TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Create orders table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE,
        user_id INTEGER,
        website_type TEXT,
        answers TEXT,
        budget TEXT,
        stage TEXT DEFAULT 'Template Selected',
        status TEXT DEFAULT 'Pending',
        created TEXT DEFAULT CURRENT_TIMESTAMP,
        order_type TEXT DEFAULT 'template',
        website_name TEXT,
        requirements TEXT,
        folder_submitted INTEGER DEFAULT 0,
        folder_submitted_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    # Create notifications table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        sender_id INTEGER DEFAULT 0,
        created TEXT DEFAULT CURRENT_TIMESTAMP,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    # Create messages table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        message TEXT,
        sender TEXT,
        created TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    # Create templates table if not exists
    cur.execute("""CREATE TABLE IF NOT EXISTS templates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        category TEXT,
        features TEXT,
        original_price REAL,
        discount_price REAL,
        has_discount INTEGER DEFAULT 0,
        tag TEXT,
        image_url TEXT,
        preview_url TEXT,
        status INTEGER DEFAULT 1,
        created TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # Check if admin exists
    cur.execute("SELECT * FROM users WHERE email=?", (ADMIN_EMAIL,))
    if not cur.fetchone():
        hashed_password = bcrypt.generate_password_hash(ADMIN_PASS).decode('utf-8')
        cur.execute("""INSERT INTO users
        (uid, fullname, email, whatsapp, gender, dob, profession, password, role)
        VALUES(?,?,?,?,?,?,?,?,?)""", (
            "ADMIN001", "Main Admin", ADMIN_EMAIL, "0000000000",
            "Male", "1990-01-01", "Administrator", hashed_password, "admin"
        ))

    # Check if templates exist
    cur.execute("SELECT COUNT(*) FROM templates")
    if cur.fetchone()[0] == 0:
        default_templates = [
            ("E-commerce", "Online stores for selling products. Includes shopping cart, payment processing, and inventory management.", "E-commerce", "Product Catalog,Shopping Cart,Payment Gateway,Inventory Management,Customer Accounts", 865, 692, 1, "Popular", "ecommerce.png", "https://demo-ecommerce.webcraftpro.com", 1),
            ("Business/Brand", "Professional websites that represent companies and build trust with customers.", "Business", "About Us,Services,Contact Form,Testimonials,Responsive Design", 450, 405, 1, "Recommended", "business.png", "https://demo-business.webcraftpro.com", 1),
            ("Blog", "Platforms for regular content publication, articles, and personal thoughts.", "Blog", "Content Management,Categories/Tags,Comments,Social Sharing,SEO Tools", 350, 350, 0, "", "blog.png", "https://demo-blog.webcraftpro.com", 1),
            ("Portfolio", "Showcase creative work such as art, design, photography to attract clients.", "Portfolio", "Gallery Display,Project Details,Client Testimonials,Contact Form,Responsive Layout", 400, 360, 1, "", "portfolio.png", "https://demo-portfolio.webcraftpro.com", 1),
            ("Educational", "Websites for courses, tutorials, and learning resources.", "Educational", "Course Management,Student Accounts,Progress Tracking,Certificates,Payment Integration", 950, 760, 1, "Best Value", "education.png", "https://demo-education.webcraftpro.com", 1),
            ("Social Media", "Platforms to connect users, share content, and build communities.", "Social Media", "User Profiles,Content Feed,Messaging,Notifications,Community Features", 1200, 960, 1, "", "social.png", "https://demo-social.webcraftpro.com", 1),
            ("News/Media", "Sites for publishing articles, news, and timely content.", "News", "Article Management,Categories,Search Function,Subscription,Advertising", 750, 675, 1, "", "news.png", "https://demo-news.webcraftpro.com", 1),
            ("Event", "Platforms to promote events, sell tickets, and manage registrations.", "Event", "Event Calendar,Ticket Sales,Registration,Payment Processing,Reminders", 550, 495, 1, "", "event.png", "https://demo-event.webcraftpro.com", 1),
            ("Forum/Community", "Discussion-based sites where users can create topics and reply to threads.", "Forum", "User Registration,Discussion Threads,Moderation Tools,Private Messaging,User Groups", 600, 540, 1, "", "forum.png", "https://demo-forum.webcraftpro.com", 1)
        ]
        
        for template in default_templates:
            cur.execute("""INSERT INTO templates 
            (name, description, category, features, original_price, discount_price, has_discount, tag, image_url, preview_url, status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", template)

    con.commit()
    con.close()
    print("✓ Database initialized successfully")

# Initialize database only once
init_db()

# ---------------- USER ----------------
class User(UserMixin):
    def __init__(self, id, email, role, fullname=""):
        self.id = id
        self.email = email
        self.role = role
        self.fullname = fullname

@login_manager.user_loader
def load_user(user_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, email, role, fullname FROM users WHERE id=?", (user_id,))
    u = cur.fetchone()
    con.close()
    return User(u[0], u[1], u[2], u[3]) if u else None

# ---------------- HELPER FUNCTIONS ----------------
def get_all_templates():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM templates WHERE status=1 ORDER BY id DESC")
    templates = cur.fetchall()
    con.close()
    return templates

def get_template_by_id(template_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM templates WHERE id=?", (template_id,))
    template = cur.fetchone()
    con.close()
    return template

def get_unread_notifications_count(user_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,))
    count = cur.fetchone()[0]
    con.close()
    return count

def get_completed_websites_count(user_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND folder_submitted=1", (user_id,))
    count = cur.fetchone()[0]
    con.close()
    return count

def get_unread_orders_count(user_id):
    con = db()
    cur = con.cursor()
    # Get orders with unread notifications
    cur.execute("""
        SELECT COUNT(DISTINCT o.id) 
        FROM orders o 
        JOIN notifications n ON o.user_id = n.user_id 
        WHERE o.user_id=? AND n.is_read=0 AND n.message LIKE '%' || o.order_id || '%'
    """, (user_id,))
    count = cur.fetchone()[0]
    con.close()
    return count

# ---------------- BASE TEMPLATE ----------------
BASE_TEMPLATE = '''
<!doctype html>
<html>
<head>
<title>{{title}}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
    :root {
        --primary: #4361ee;
        --primary-dark: #3a56d4;
        --primary-light: #5a75f0;
        --secondary: #06d6a0;
        --secondary-dark: #05c090;
        --accent: #ffd166;
        --accent-dark: #ffc43d;
        --danger: #ef476f;
        --warning: #ffd166;
        --info: #118ab2;
        --light: #f8f9fa;
        --dark: #212529;
        --gradient-1: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
        --gradient-2: linear-gradient(135deg, #7209b7 0%, #f72585 100%);
        --gradient-3: linear-gradient(135deg, #4cc9f0 0%, #4361ee 100%);
        --gradient-4: linear-gradient(135deg, #06d6a0 0%, #4cc9f0 100%);
        --shadow-sm: 0 2px 4px rgba(0,0,0,0.05);
        --shadow-md: 0 4px 6px rgba(0,0,0,0.07);
        --shadow-lg: 0 10px 25px rgba(0,0,0,0.1);
        --shadow-xl: 0 20px 40px rgba(0,0,0,0.15);
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 16px;
        --radius-xl: 24px;
        --radius-2xl: 32px;
    }
    
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
        -webkit-tap-highlight-color: transparent;
        -webkit-touch-callout: none;
        -webkit-user-select: none;
        -moz-user-select: none;
        -ms-user-select: none;
        user-select: none;
        touch-action: manipulation;
    }
    
    html, body {
        width: 100%;
        height: 100%;
        overflow-x: hidden;
        font-family: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    }
    
    body {
        background: linear-gradient(135deg, #0c0c0c 0%, #1a1a1a 100%);
        position: relative;
        overflow-x: hidden;
    }
    
    /* Animated Background */
    .animated-bg {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: -2;
        overflow: hidden;
    }
    
    .floating-shapes {
        position: absolute;
        width: 100%;
        height: 100%;
        filter: blur(60px);
        opacity: 0.1;
    }
    
    .shape-1 {
        position: absolute;
        top: 10%;
        left: 10%;
        width: 300px;
        height: 300px;
        background: var(--primary);
        border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%;
        animation: float 25s infinite ease-in-out;
    }
    
    .shape-2 {
        position: absolute;
        top: 60%;
        right: 10%;
        width: 250px;
        height: 250px;
        background: var(--secondary);
        border-radius: 70% 30% 30% 70% / 70% 70% 30% 30%;
        animation: float 30s infinite ease-in-out reverse;
    }
    
    .shape-3 {
        position: absolute;
        bottom: 10%;
        left: 20%;
        width: 200px;
        height: 200px;
        background: var(--accent);
        border-radius: 50% 50% 30% 70% / 50% 30% 70% 50%;
        animation: float 35s infinite ease-in-out;
    }
    
    .particles {
        position: absolute;
        width: 100%;
        height: 100%;
    }
    
    .particle {
        position: absolute;
        background: rgba(255, 255, 255, 0.05);
        border-radius: 50%;
        animation: float 15s infinite ease-in-out;
    }
    
    /* Fog Effect */
    .fog-container {
        position: fixed;
        width: 100%;
        height: 100%;
        overflow: hidden;
        z-index: -1;
        opacity: 0.1;
    }
    
    .fog {
        position: absolute;
        width: 200%;
        height: 100%;
        background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(255,255,255,0.05) 50%, 
            transparent 100%);
        animation: fogMove 60s infinite linear;
    }
    
    .fog-2 {
        animation: fogMove 40s infinite linear reverse;
        opacity: 0.08;
    }
    
    @keyframes fogMove {
        0% { transform: translateX(-50%); }
        100% { transform: translateX(50%); }
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0) rotate(0deg); }
        33% { transform: translateY(-30px) rotate(120deg); }
        66% { transform: translateY(30px) rotate(240deg); }
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    
    @keyframes slideInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes slideInLeft {
        from {
            opacity: 0;
            transform: translateX(-30px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(30px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    
    @keyframes scaleIn {
        from {
            opacity: 0;
            transform: scale(0.9);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }
    
    @keyframes glow {
        0%, 100% {
            box-shadow: 0 0 20px rgba(67, 97, 238, 0.3);
        }
        50% {
            box-shadow: 0 0 30px rgba(67, 97, 238, 0.5);
        }
    }
    
    @keyframes shimmer {
        0% {
            background-position: -1000px 0;
        }
        100% {
            background-position: 1000px 0;
        }
    }
    
    @keyframes bounce {
        0%, 100% {
            transform: translateY(0);
        }
        50% {
            transform: translateY(-10px);
        }
    }
    
    .animate-float {
        animation: float 6s ease-in-out infinite;
    }
    
    .animate-pulse {
        animation: pulse 2s ease-in-out infinite;
    }
    
    .animate-slide-up {
        animation: slideInUp 0.6s ease-out;
    }
    
    .animate-slide-left {
        animation: slideInLeft 0.6s ease-out;
    }
    
    .animate-slide-right {
        animation: slideInRight 0.6s ease-out;
    }
    
    .animate-fade-in {
        animation: fadeIn 0.5s ease-out;
    }
    
    .animate-scale-in {
        animation: scaleIn 0.4s ease-out;
    }
    
    .animate-glow {
        animation: glow 2s ease-in-out infinite;
    }
    
    .animate-bounce {
        animation: bounce 1s ease-in-out infinite;
    }
    
    /* Glass Morphism */
    .glass {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .glass-dark {
        background: rgba(30, 30, 30, 0.85);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Notification System */
    .notification-container {
        position: fixed;
        top: 80px;
        right: 20px;
        z-index: 9999;
        max-width: 350px;
        width: 100%;
    }
    
    .notification {
        background: rgba(255, 255, 255, 0.98);
        backdrop-filter: blur(10px);
        border-radius: var(--radius-md);
        padding: 15px;
        margin-bottom: 10px;
        box-shadow: var(--shadow-lg);
        animation: slideInRight 0.3s ease-out, fadeIn 0.3s ease-out;
        display: flex;
        align-items: center;
        gap: 12px;
        border-left: 4px solid var(--primary);
        transform-origin: right;
    }
    
    .notification.success {
        border-left-color: var(--secondary);
    }
    
    .notification.warning {
        border-left-color: var(--warning);
    }
    
    .notification.error {
        border-left-color: var(--danger);
    }
    
    .notification.info {
        border-left-color: var(--info);
    }
    
    .notification-icon {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        flex-shrink: 0;
    }
    
    .notification.success .notification-icon {
        background: rgba(6, 214, 160, 0.1);
        color: var(--secondary);
    }
    
    .notification.warning .notification-icon {
        background: rgba(255, 209, 102, 0.1);
        color: var(--warning);
    }
    
    .notification.error .notification-icon {
        background: rgba(239, 71, 111, 0.1);
        color: var(--danger);
    }
    
    .notification.info .notification-icon {
        background: rgba(67, 97, 238, 0.1);
        color: var(--primary);
    }
    
    .notification-content {
        flex: 1;
    }
    
    .notification-title {
        font-weight: 600;
        font-size: 14px;
        margin-bottom: 2px;
        color: var(--dark);
    }
    
    .notification-message {
        font-size: 13px;
        color: #666;
        line-height: 1.4;
    }
    
    .notification-close {
        background: none;
        border: none;
        color: #999;
        cursor: pointer;
        padding: 4px;
        transition: color 0.2s;
    }
    
    .notification-close:hover {
        color: #666;
    }
    
    /* Navbar */
    .navbar {
        background: rgba(255, 255, 255, 0.98) !important;
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-bottom: 1px solid rgba(0,0,0,0.05);
        box-shadow: var(--shadow-sm);
        padding: 15px 0;
        position: sticky;
        top: 0;
        z-index: 1000;
        animation: slideInUp 0.4s ease-out;
    }
    
    .navbar-brand {
        font-weight: 800;
        font-size: 24px;
        background: linear-gradient(45deg, var(--primary), var(--primary-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .navbar-brand i {
        font-size: 28px;
        background: linear-gradient(45deg, var(--primary), var(--primary-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Badge for unread items */
    .badge-notification {
        position: absolute;
        top: -5px;
        right: -5px;
        background: var(--danger);
        color: white;
        border-radius: 50%;
        width: 18px;
        height: 18px;
        font-size: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: pulse 1.5s infinite;
    }
    
    /* Main Container */
    .main-container {
        background: transparent;
        min-height: calc(100vh - 70px);
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
        padding: 20px;
        padding-bottom: 80px; /* Space for bottom nav */
    }
    
    /* Fix scroll for mobile */
    @supports (-webkit-touch-callout: none) {
        .main-container {
            min-height: -webkit-fill-available;
        }
    }
    
    /* Content Wrapper */
    .content-wrapper {
        max-width: 1400px;
        margin: 0 auto;
        width: 100%;
    }
    
    /* Card Styles */
    .card {
        background: rgba(255, 255, 255, 0.98);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-lg);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        overflow: hidden;
    }
    
    .card:hover {
        transform: translateY(-4px);
        box-shadow: var(--shadow-xl);
    }
    
    .card-header {
        background: transparent;
        border-bottom: 1px solid rgba(0,0,0,0.05);
        padding: 20px;
    }
    
    .card-body {
        padding: 20px;
    }
    
    /* Button Styles */
    .btn {
        border-radius: var(--radius-md);
        font-weight: 500;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .btn::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 50%;
        transform: translate(-50%, -50%);
        transition: width 0.6s, height 0.6s;
    }
    
    .btn:hover::before {
        width: 300px;
        height: 300px;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        border: none;
        color: white;
    }
    
    .btn-primary:hover {
        background: linear-gradient(135deg, var(--primary-dark), var(--primary));
        transform: translateY(-2px);
        box-shadow: 0 10px 25px rgba(67, 97, 238, 0.3);
    }
    
    .btn-success {
        background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
        border: none;
    }
    
    .btn-success:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 25px rgba(6, 214, 160, 0.3);
    }
    
    /* Form Styles */
    .form-control {
        border: 2px solid #e2e8f0;
        border-radius: var(--radius-md);
        padding: 12px 15px;
        font-size: 14px;
        transition: all 0.3s;
        background: white;
        color: #333;
    }
    
    .form-control:focus {
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.1);
        outline: none;
    }
    
    .form-control-lg {
        padding: 16px 20px;
        font-size: 16px;
    }
    
    input[type="date"] {
        position: relative;
        color: #333;
    }
    
    input[type="date"]::-webkit-calendar-picker-indicator {
        background: transparent;
        bottom: 0;
        color: transparent;
        cursor: pointer;
        height: auto;
        left: 0;
        position: absolute;
        right: 0;
        top: 0;
        width: auto;
    }
    
    /* Template Grid */
    .template-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 25px;
        padding: 20px 0;
    }
    
    .template-card {
        background: white;
        border-radius: var(--radius-lg);
        overflow: hidden;
        box-shadow: var(--shadow-lg);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        height: 100%;
        display: flex;
        flex-direction: column;
        animation: scaleIn 0.5s ease-out;
        animation-fill-mode: both;
    }
    
    .template-card:nth-child(1) { animation-delay: 0.1s; }
    .template-card:nth-child(2) { animation-delay: 0.2s; }
    .template-card:nth-child(3) { animation-delay: 0.3s; }
    .template-card:nth-child(4) { animation-delay: 0.4s; }
    .template-card:nth-child(5) { animation-delay: 0.5s; }
    .template-card:nth-child(6) { animation-delay: 0.6s; }
    
    .template-card:hover {
        transform: translateY(-8px) scale(1.02);
        box-shadow: var(--shadow-xl);
    }
    
    .template-image {
        height: 200px;
        background: linear-gradient(135deg, #2a2a2a, #1a1a1a);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 48px;
        position: relative;
        overflow: hidden;
    }
    
    .template-image img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 0.5s;
    }
    
    .template-card:hover .template-image img {
        transform: scale(1.05);
    }
    
    .template-image::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, 
            transparent 30%, 
            rgba(255,255,255,0.1) 50%, 
            transparent 70%);
        animation: shimmer 3s infinite linear;
        z-index: 1;
    }
    
    .template-badge {
        position: absolute;
        top: 15px;
        left: 15px;
        background: rgba(255, 255, 255, 0.95);
        color: var(--primary);
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        box-shadow: var(--shadow-sm);
        z-index: 2;
    }
    
    .template-price {
        position: absolute;
        top: 15px;
        right: 15px;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 8px 16px;
        border-radius: var(--radius-md);
        font-size: 14px;
        font-weight: 600;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        z-index: 2;
    }
    
    .original-price {
        text-decoration: line-through;
        color: #94a3b8;
        font-size: 12px;
        margin-bottom: 2px;
    }
    
    .discount-price {
        color: white;
        font-size: 18px;
        font-weight: 700;
    }
    
    .template-content {
        padding: 20px;
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    
    .template-title {
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 10px;
        color: #1e293b;
    }
    
    .template-description {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 15px;
        line-height: 1.5;
        flex: 1;
    }
    
    .template-features {
        list-style: none;
        padding: 0;
        margin: 0 0 20px 0;
    }
    
    .template-features li {
        font-size: 12px;
        color: #64748b;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
    }
    
    .template-features li i {
        color: var(--secondary);
        margin-right: 8px;
        font-size: 10px;
    }
    
    .template-buttons {
        display: flex;
        gap: 10px;
        margin-top: auto;
    }
    
    .template-button {
        flex: 1;
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        color: white;
        border: none;
        border-radius: var(--radius-md);
        padding: 12px;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
        text-decoration: none;
        display: block;
        transition: all 0.3s;
    }
    
    .template-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(67, 97, 238, 0.3);
        color: white;
    }
    
    .preview-button {
        background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
    }
    
    /* Chat Interface */
    .chat-wrapper {
        height: calc(100vh - 140px);
        display: flex;
        flex-direction: column;
        background: white;
        border-radius: var(--radius-lg);
        overflow: hidden;
        box-shadow: var(--shadow-xl);
    }
    
    .chat-header {
        padding: 20px;
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        color: white;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    
    .chat-messages {
        flex: 1;
        overflow-y: auto;
        padding: 20px;
        background: #f8f9fa;
        -webkit-overflow-scrolling: touch;
        display: flex;
        flex-direction: column;
        gap: 15px;
    }
    
    .chat-message {
        max-width: 80%;
        padding: 12px 18px;
        border-radius: var(--radius-lg);
        animation: slideInUp 0.3s ease-out;
        position: relative;
        word-break: break-word;
    }
    
    .user-message {
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        color: white;
        margin-left: auto;
        border-bottom-right-radius: 4px;
        box-shadow: var(--shadow-md);
    }
    
    .bot-message {
        background: white;
        color: #1e293b;
        margin-right: auto;
        border-bottom-left-radius: 4px;
        box-shadow: var(--shadow-sm);
        border: 1px solid #e2e8f0;
    }
    
    .chat-input-wrapper {
        padding: 20px;
        background: white;
        border-top: 1px solid #e2e8f0;
        display: flex;
        gap: 10px;
        align-items: flex-end;
    }
    
    .chat-input {
        flex: 1;
        border: 2px solid #e2e8f0;
        border-radius: var(--radius-md);
        padding: 12px 15px;
        font-size: 14px;
        resize: none;
        transition: all 0.3s;
    }
    
    .chat-input:focus {
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.1);
        outline: none;
    }
    
    .chat-send-btn {
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        border: none;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.3s;
    }
    
    .chat-send-btn:hover {
        transform: scale(1.1);
        box-shadow: 0 8px 20px rgba(67, 97, 238, 0.3);
    }
    
    /* Progress Bar */
    .progress-container {
        width: 100%;
        height: 8px;
        background: #e2e8f0;
        border-radius: 4px;
        overflow: hidden;
        margin: 20px 0;
    }
    
    .progress-bar {
        height: 100%;
        background: linear-gradient(90deg, var(--primary), var(--secondary));
        border-radius: 4px;
        transition: width 0.6s ease;
        position: relative;
        overflow: hidden;
    }
    
    .progress-bar::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(90deg, 
            transparent 30%, 
            rgba(255,255,255,0.3) 50%, 
            transparent 70%);
        animation: shimmer 2s infinite linear;
    }
    
    /* Navigation Bottom */
    .nav-bottom {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(255, 255, 255, 0.98);
        backdrop-filter: blur(20px);
        padding: 10px 0;
        display: flex;
        justify-content: space-around;
        border-top: 1px solid rgba(0,0,0,0.05);
        box-shadow: 0 -2px 20px rgba(0,0,0,0.1);
        z-index: 1000;
    }
    
    .nav-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-decoration: none;
        color: #64748b;
        padding: 8px 12px;
        border-radius: var(--radius-md);
        transition: all 0.3s;
        position: relative;
    }
    
    .nav-item.active {
        color: var(--primary);
        background: rgba(67, 97, 238, 0.1);
    }
    
    .nav-item.active::after {
        content: '';
        position: absolute;
        top: -4px;
        width: 6px;
        height: 6px;
        background: var(--primary);
        border-radius: 50%;
    }
    
    .nav-icon {
        font-size: 20px;
        margin-bottom: 4px;
    }
    
    .nav-label {
        font-size: 11px;
        font-weight: 500;
    }
    
    /* Hero Section */
    .hero-section {
        min-height: 70vh;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: white;
        padding: 40px 20px;
        position: relative;
        overflow: hidden;
    }
    
    .hero-content {
        max-width: 800px;
        margin: 0 auto;
        animation: slideInUp 0.8s ease-out;
        background: rgba(30, 30, 30, 0.7);
        backdrop-filter: blur(10px);
        padding: 40px;
        border-radius: var(--radius-xl);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .hero-title {
        font-size: 3.5rem;
        font-weight: 800;
        margin-bottom: 20px;
        background: linear-gradient(45deg, white, var(--primary-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .hero-subtitle {
        font-size: 1.2rem;
        color: #cbd5e1;
        margin-bottom: 30px;
        line-height: 1.6;
    }
    
    /* Auth Pages */
    .auth-container {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 20px;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
    }
    
    .auth-card {
        background: rgba(255, 255, 255, 0.98);
        backdrop-filter: blur(20px);
        border-radius: var(--radius-xl);
        overflow: hidden;
        box-shadow: var(--shadow-xl);
        width: 100%;
        max-width: 450px;
        animation: scaleIn 0.6s ease-out;
        border: 1px solid rgba(0, 0, 0, 0.05);
    }
    
    .auth-header {
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        color: white;
        padding: 30px;
        text-align: center;
    }
    
    .auth-body {
        padding: 30px;
    }
    
    /* Order Summary */
    .order-summary-card {
        background: linear-gradient(135deg, #f8fafc, #f1f5f9);
        border: none;
        border-radius: var(--radius-lg);
        padding: 25px;
        margin-bottom: 25px;
    }
    
    /* Stats Cards */
    .stats-card {
        border: none;
        border-radius: var(--radius-lg);
        padding: 25px;
        text-align: center;
        color: white;
        position: relative;
        overflow: hidden;
        transition: transform 0.3s;
    }
    
    .stats-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, 
            transparent 30%, 
            rgba(255,255,255,0.1) 50%, 
            transparent 70%);
        animation: shimmer 3s infinite linear;
    }
    
    .stats-card:hover {
        transform: translateY(-5px);
    }
    
    /* Responsive Design */
    @media (max-width: 768px) {
        .hero-title {
            font-size: 2.5rem;
        }
        
        .hero-content {
            padding: 30px 20px;
        }
        
        .template-grid {
            grid-template-columns: 1fr;
            gap: 20px;
        }
        
        .chat-wrapper {
            height: calc(100vh - 120px);
        }
        
        .navbar-brand {
            font-size: 20px;
        }
        
        .main-container {
            padding: 15px;
            padding-bottom: 70px;
        }
        
        .notification-container {
            right: 10px;
            left: 10px;
            max-width: none;
        }
        
        .auth-card {
            max-width: 90%;
        }
        
        .template-buttons {
            flex-direction: column;
        }
    }
    
    @media (max-width: 480px) {
        .hero-title {
            font-size: 2rem;
        }
        
        .hero-subtitle {
            font-size: 1rem;
        }
        
        .chat-message {
            max-width: 90%;
        }
        
        .nav-item {
            padding: 6px 8px;
        }
        
        .nav-icon {
            font-size: 18px;
        }
        
        .nav-label {
            font-size: 10px;
        }
        
        .auth-header {
            padding: 20px;
        }
        
        .auth-body {
            padding: 20px;
        }
    }
    
    /* Custom Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(0,0,0,0.05);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--primary);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--primary-dark);
    }
    
    /* Loading Animation */
    .loading-spinner {
        width: 50px;
        height: 50px;
        border: 3px solid rgba(67, 97, 238, 0.1);
        border-radius: 50%;
        border-top-color: var(--primary);
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* Floating Action Button */
    .fab {
        position: fixed;
        bottom: 80px;
        right: 20px;
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: linear-gradient(135deg, var(--primary), var(--primary-dark));
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        box-shadow: var(--shadow-xl);
        cursor: pointer;
        z-index: 1000;
        animation: bounce 2s infinite;
    }
    
    .fab:hover {
        transform: scale(1.1);
    }
    
    /* Admin Table */
    .admin-table {
        width: 100%;
        border-collapse: collapse;
    }
    
    .admin-table th {
        background: #f8f9fa;
        padding: 12px;
        text-align: left;
        font-weight: 600;
        border-bottom: 2px solid #dee2e6;
    }
    
    .admin-table td {
        padding: 12px;
        border-bottom: 1px solid #dee2e6;
        vertical-align: middle;
    }
    
    .admin-table tr:hover {
        background: #f8f9fa;
    }
    
    /* Image Preview */
    .image-preview {
        width: 80px;
        height: 60px;
        object-fit: cover;
        border-radius: var(--radius-sm);
        border: 1px solid #dee2e6;
    }
    
    /* Form Groups */
    .form-group {
        margin-bottom: 1rem;
    }
    
    .form-group label {
        display: block;
        margin-bottom: 0.5rem;
        font-weight: 500;
        color: #333;
    }
    
    /* Badge Styles */
    .badge {
        display: inline-block;
        padding: 4px 8px;
        font-size: 12px;
        font-weight: 600;
        line-height: 1;
        text-align: center;
        white-space: nowrap;
        vertical-align: baseline;
        border-radius: 10px;
    }
    
    .badge-success {
        background-color: var(--secondary);
        color: white;
    }
    
    .badge-danger {
        background-color: var(--danger);
        color: white;
    }
    
    .badge-warning {
        background-color: var(--warning);
        color: #333;
    }
    
    .badge-info {
        background-color: var(--info);
        color: white;
    }
    
    /* Alert Messages */
    .alert {
        padding: 12px 16px;
        border-radius: var(--radius-md);
        margin-bottom: 1rem;
        border: 1px solid transparent;
    }
    
    .alert-success {
        background-color: rgba(6, 214, 160, 0.1);
        border-color: var(--secondary);
        color: var(--secondary-dark);
    }
    
    .alert-danger {
        background-color: rgba(239, 71, 111, 0.1);
        border-color: var(--danger);
        color: var(--danger);
    }
    
    .alert-info {
        background-color: rgba(67, 97, 238, 0.1);
        border-color: var(--primary);
        color: var(--primary-dark);
    }
    
    /* Action Buttons */
    .action-buttons {
        display: flex;
        gap: 5px;
    }
    
    .btn-sm {
        padding: 6px 12px;
        font-size: 12px;
    }
    
    /* Pagination */
    .pagination {
        display: flex;
        justify-content: center;
        gap: 5px;
        margin-top: 20px;
    }
    
    .page-link {
        padding: 8px 12px;
        border: 1px solid #dee2e6;
        border-radius: var(--radius-sm);
        color: var(--primary);
        text-decoration: none;
        transition: all 0.3s;
    }
    
    .page-link:hover {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
    }
    
    .page-link.active {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
    }
</style>
</head>
<body>

<!-- Animated Background -->
<div class="animated-bg">
    <div class="floating-shapes">
        <div class="shape-1"></div>
        <div class="shape-2"></div>
        <div class="shape-3"></div>
    </div>
    <div class="fog-container">
        <div class="fog"></div>
        <div class="fog fog-2"></div>
    </div>
    <div class="particles">
        <!-- Particles will be generated by JavaScript -->
    </div>
</div>

<!-- Notification Container -->
<div class="notification-container" id="notificationContainer"></div>

<nav class="navbar navbar-expand-lg navbar-light">
  <div class="container">
    <a class="navbar-brand" href="/">
      <i class="fas fa-code"></i>
      <span>WebCraft Pro</span>
    </a>
    {% if current_user.is_authenticated %}
    <div class="d-flex align-items-center">
      {% if current_user.role == 'admin' %}
      <span class="admin-badge me-2 d-none d-md-inline" style="background: linear-gradient(45deg, #ef476f, #ff9e6d); color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">
        <i class="fas fa-crown me-1"></i>Admin
      </span>
      <a href="/admin" class="btn btn-danger btn-sm me-2">
        <i class="fas fa-user-shield me-1"></i>Admin Panel
      </a>
      {% endif %}
      <span class="me-2 text-dark d-none d-md-block" style="font-weight: 500;">
        <i class="fas fa-user-circle me-1"></i>{{ current_user.email[:15] }}{% if current_user.email|length > 15 %}...{% endif %}
      </span>
      <a href="/logout" class="btn btn-outline-danger btn-sm">
        <i class="fas fa-sign-out-alt me-1"></i>Logout
      </a>
    </div>
    {% else %}
    <div class="d-flex align-items-center">
      <a href="/login" class="btn btn-outline-primary btn-sm me-2">
        <i class="fas fa-sign-in-alt me-1"></i>Login
      </a>
      <a href="/signup" class="btn btn-primary btn-sm">
        <i class="fas fa-user-plus me-1"></i>Signup
      </a>
    </div>
    {% endif %}
  </div>
</nav>

<div class="main-container">
  {{ content | safe }}
</div>

{% if current_user.is_authenticated and not request.path.startswith('/admin') and request.path != '/custom-web' and request.path != '/login' and request.path != '/signup' and request.path != '/' %}
<div class="nav-bottom animate-slide-up">
  <a href="/dashboard" class="nav-item {% if request.path == '/dashboard' %}active{% endif %}">
    <i class="fas fa-th-large nav-icon"></i>
    <span class="nav-label">Templates</span>
  </a>
  <a href="/custom-web" class="nav-item {% if request.path == '/custom-web' %}active{% endif %}">
    <i class="fas fa-pencil-ruler nav-icon"></i>
    <span class="nav-label">Custom</span>
  </a>
  <a href="/orders" class="nav-item {% if request.path == '/orders' %}active{% endif %}">
    <i class="fas fa-shopping-cart nav-icon"></i>
    <span class="nav-label">Orders</span>
    {% if unread_orders_count and unread_orders_count > 0 %}
    <span class="badge-notification">{{ unread_orders_count }}</span>
    {% endif %}
  </a>
  <a href="/account" class="nav-item {% if request.path == '/account' %}active{% endif %}">
    <i class="fas fa-user nav-icon"></i>
    <span class="nav-label">Account</span>
  </a>
</div>
{% endif %}

<!-- Floating Action Button for Mobile -->
{% if current_user.is_authenticated %}
<div class="fab d-md-none">
  <i class="fas fa-plus"></i>
</div>
{% endif %}

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
    // Generate particles for background
    function createParticles() {
        const particlesContainer = document.querySelector('.particles');
        const particleCount = 50;
        
        for (let i = 0; i < particleCount; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            
            // Random size and position
            const size = Math.random() * 4 + 1;
            const posX = Math.random() * 100;
            const posY = Math.random() * 100;
            const delay = Math.random() * 20;
            const duration = 15 + Math.random() * 20;
            
            particle.style.width = size + 'px';
            particle.style.height = size + 'px';
            particle.style.left = posX + '%';
            particle.style.top = posY + '%';
            particle.style.animationDelay = delay + 's';
            particle.style.animationDuration = duration + 's';
            
            // Random color
            const colors = [
                'rgba(67, 97, 238, 0.3)',
                'rgba(6, 214, 160, 0.3)',
                'rgba(255, 209, 102, 0.3)',
                'rgba(239, 71, 111, 0.3)'
            ];
            particle.style.background = colors[Math.floor(Math.random() * colors.length)];
            
            particlesContainer.appendChild(particle);
        }
    }
    
    // Notification System
    function showNotification(type, title, message, duration = 5000) {
        const container = document.getElementById('notificationContainer');
        const notification = document.createElement('div');
        notification.className = 'notification ' + type;
        
        const icons = {
            success: 'fas fa-check-circle',
            warning: 'fas fa-exclamation-triangle',
            error: 'fas fa-times-circle',
            info: 'fas fa-info-circle'
        };
        
        notification.innerHTML = `
            <div class="notification-icon">
                <i class="${icons[type]}"></i>
            </div>
            <div class="notification-content">
                <div class="notification-title">${title}</div>
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        container.appendChild(notification);
        
        // Auto remove after duration
        setTimeout(() => {
            if (notification.parentNode === container) {
                notification.style.animation = 'slideInRight 0.3s ease-out reverse';
                setTimeout(() => notification.remove(), 300);
            }
        }, duration);
    }
    
    // Chat functionality
    function setupChat() {
        const chatMessages = document.querySelector('.chat-messages');
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Auto resize textareas
            const textareas = document.querySelectorAll('textarea');
            textareas.forEach(textarea => {
                textarea.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = (this.scrollHeight) + 'px';
                });
            });
            
            // Smooth scroll to bottom on new messages
            const observer = new MutationObserver(() => {
                chatMessages.scrollTo({
                    top: chatMessages.scrollHeight,
                    behavior: 'smooth'
                });
            });
            
            observer.observe(chatMessages, { childList: true });
        }
    }
    
    // Form validation with notifications
    function setupFormValidation() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', function(e) {
                const requiredFields = this.querySelectorAll('[required]');
                let isValid = true;
                
                requiredFields.forEach(field => {
                    if (!field.value.trim()) {
                        isValid = false;
                        field.classList.add('is-invalid');
                        
                        // Add error styling
                        const errorMsg = document.createElement('div');
                        errorMsg.className = 'invalid-feedback';
                        errorMsg.textContent = 'This field is required';
                        
                        if (!field.nextElementSibling || !field.nextElementSibling.classList.contains('invalid-feedback')) {
                            field.parentNode.insertBefore(errorMsg, field.nextSibling);
                        }
                        
                        // Show notification
                        showNotification('error', 'Validation Error', 'Please fill in all required fields');
                    } else {
                        field.classList.remove('is-invalid');
                        const errorMsg = field.nextElementSibling;
                        if (errorMsg && errorMsg.classList.contains('invalid-feedback')) {
                            errorMsg.remove();
                        }
                    }
                });
                
                if (!isValid) {
                    e.preventDefault();
                    return false;
                }
                
                // Show success notification
                showNotification('success', 'Success', 'Form submitted successfully');
            });
        });
    }
    
    // Initialize animations
    function initAnimations() {
        // Animate elements on scroll
        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        };
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-slide-up');
                }
            });
        }, observerOptions);
        
        // Observe all cards and sections
        document.querySelectorAll('.template-card, .card, section').forEach(el => {
            observer.observe(el);
        });
    }
    
    // Fix for iOS scroll
    function fixIOSScroll() {
        if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
            document.body.style.height = '100%';
            document.body.style.overflow = 'auto';
            document.body.style.webkitOverflowScrolling = 'touch';
        }
    }
    
    // Disable zooming for mobile
    document.addEventListener('wheel', function(e) {
        if (e.ctrlKey) {
            e.preventDefault();
        }
    }, { passive: false });
    
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && (e.key === '+' || e.key === '-' || e.key === '0')) {
            e.preventDefault();
        }
    });
    
    document.addEventListener('touchstart', function(e) {
        if (e.touches.length > 1) {
            e.preventDefault();
        }
    }, { passive: false });
    
    let lastTouchEnd = 0;
    document.addEventListener('touchend', function(e) {
        const now = (new Date()).getTime();
        if (now - lastTouchEnd <= 300) {
            e.preventDefault();
        }
        lastTouchEnd = now;
    }, false);
    
    // Prevent double tap zoom
    document.addEventListener('dblclick', function(e) {
        e.preventDefault();
    }, { passive: false });
    
    // Fab button functionality
    const fab = document.querySelector('.fab');
    if (fab) {
        fab.addEventListener('click', function() {
            const navItems = document.querySelectorAll('.nav-item');
            const currentPath = window.location.pathname;
            let targetUrl = '/dashboard';
            
            navItems.forEach(item => {
                if (item.classList.contains('active')) {
                    const href = item.getAttribute('href');
                    if (href !== currentPath) {
                        targetUrl = href;
                    }
                }
            });
            
            window.location.href = targetUrl;
        });
    }
    
    // Login prompt function
    function showLoginPrompt() {
        showNotification('info', 'Login Required', 'Please login to access this feature', 3000);
    }
    
    // Check if user is logged in for protected actions
    document.addEventListener('click', function(e) {
        const target = e.target;
        const protectedActions = ['/order-template/', '/custom-web', '/orders', '/account'];
        const isProtected = protectedActions.some(action => 
            target.href && target.href.includes(action) || 
            target.closest('a') && target.closest('a').href && target.closest('a').href.includes(action)
        );
        
        {% if not current_user.is_authenticated %}
        if (isProtected && !window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/signup')) {
            e.preventDefault();
            showLoginPrompt();
        }
        {% endif %}
    });
    
    // Preview website function
    function previewWebsite(url) {
        if (url) {
            window.open(url, '_blank');
        } else {
            showNotification('info', 'Preview', 'No preview URL available for this template');
        }
    }
    
    // Initialize everything when DOM is loaded
    document.addEventListener('DOMContentLoaded', function() {
        createParticles();
        setupChat();
        setupFormValidation();
        initAnimations();
        fixIOSScroll();
        
        // Adjust chat input height
        const chatInputs = document.querySelectorAll('.chat-input');
        chatInputs.forEach(input => {
            input.style.height = 'auto';
            input.style.height = (input.scrollHeight) + 'px';
        });
        
        // Show welcome notification for new users
        {% if current_user.is_authenticated and session.get('show_welcome', True) %}
        showNotification('success', 'Welcome back!', 'Great to see you again, {{ current_user.fullname or current_user.email }}!', 3000);
        {% endif %}
        
        // Fix for iOS keyboard
        if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
            const inputs = document.querySelectorAll('input, textarea');
            inputs.forEach(input => {
                input.addEventListener('focus', function() {
                    window.scrollTo(0, this.offsetTop - 100);
                });
            });
        }
    });
</script>
{{ scripts | safe if scripts }}
</body>
</html>
'''

def render_base_template(title, content, unread_orders_count=0, scripts=""):
    """Helper function to render the base template"""
    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        content=content,
        unread_orders_count=unread_orders_count,
        scripts=scripts
    )

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect("/dashboard")
    
    templates = get_all_templates()
    
    template_cards = ""
    for template in templates:
        id, name, description, category, features_str, original_price, discount_price, has_discount, tag, image_url, preview_url, status, created = template
        
        features = features_str.split(',') if features_str else []
        
        price_html = ""
        if has_discount:
            price_html = f'''
            <div class="template-price">
                <span class="original-price">${original_price}</span>
                <span class="discount-price">${discount_price}</span>
            </div>
            '''
        else:
            price_html = f'''
            <div class="template-price">
                <span class="discount-price">${original_price}</span>
            </div>
            '''
        
        tag_html = f'<div class="template-badge">{tag}</div>' if tag else ""
        
        features_html = "".join([f'<li><i class="fas fa-check"></i> {feature}</li>' for feature in features[:3]])
        
        # Check if image exists
        if image_url and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], image_url)):
            image_html = f'<img src="/static/uploads/{image_url}" alt="{name}">'
        else:
            image_html = f'<i class="fas fa-image fa-3x"></i><p class="mt-2">{name}</p>'
        
        template_cards += f'''
        <div class="template-card">
            <div class="template-image">
                {image_html}
                {tag_html}
                {price_html}
            </div>
            <div class="template-content">
                <h3 class="template-title">{name}</h3>
                <p class="template-description">{description}</p>
                <ul class="template-features">
                    {features_html}
                </ul>
                <div class="template-buttons">
                    <a href="{preview_url}" target="_blank" class="template-button preview-button">
                        <i class="fas fa-eye me-2"></i>Preview
                    </a>
                    <a href="/login" class="template-button" onclick="showNotification('info', 'Login Required', 'Please login to order templates'); return false;">
                        <i class="fas fa-shopping-cart me-2"></i>Order Now
                    </a>
                </div>
            </div>
        </div>
        '''
    
    return render_base_template("Home", f'''
    <div class="content-wrapper">
        <div class="hero-section">
            <div class="hero-content">
                <h1 class="hero-title animate-slide-up">WebCraft Pro</h1>
                <p class="hero-subtitle animate-slide-up" style="animation-delay: 0.2s">Build stunning websites with our professional templates and custom solutions</p>
                <div class="d-flex justify-content-center gap-3 animate-slide-up" style="animation-delay: 0.4s">
                    <a href="/signup" class="btn btn-light btn-lg px-5 py-3" style="background: white; color: var(--primary-dark); font-weight: 600;">
                        <i class="fas fa-rocket me-2 animate-bounce"></i>Get Started
                    </a>
                    <a href="/login" class="btn btn-outline-light btn-lg px-5 py-3" style="border: 2px solid rgba(255,255,255,0.3);">
                        <i class="fas fa-sign-in-alt me-2"></i>Login
                    </a>
                </div>
            </div>
        </div>
        
        <div class="row justify-content-center animate-scale-in">
            <div class="col-12">
                <div class="card" style="background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(20px);">
                    <div class="card-body">
                        <h3 class="text-center mb-4" style="color: #1e293b;">Featured Templates</h3>
                        <div class="template-grid">
                            {template_cards}
                        </div>
                        <div class="text-center mt-4">
                            <a href="/signup" class="btn btn-primary btn-lg px-5">
                                <i class="fas fa-th-large me-2"></i>View All Templates
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    ''')

@app.route("/signup", methods=["GET","POST"])
def signup():
    if current_user.is_authenticated:
        return redirect("/dashboard")
        
    if request.method=="POST":
        con = db()
        try:
            cur = con.cursor()
            
            # Check if email exists
            cur.execute("SELECT id FROM users WHERE email=?", (request.form["email"],))
            if cur.fetchone():
                con.close()
                return render_base_template("Signup", f"""
                <div class="auth-container">
                    <div class="auth-card">
                        <div class="auth-header">
                            <h3>Create Account</h3>
                            <p class="mb-0">Join our community of web enthusiasts</p>
                        </div>
                        <div class="auth-body">
                            <div class="alert alert-danger">
                                <i class="fas fa-exclamation-circle me-2"></i>
                                Email already exists. Please use a different email.
                            </div>
                            <form method="post">
                                <div class="mb-3">
                                    <div class="input-group input-group-lg">
                                        <span class="input-group-text"><i class="fas fa-user"></i></span>
                                        <input name="fullname" class="form-control" placeholder="Full Name" required value='{request.form.get("fullname", "")}'>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <div class="input-group input-group-lg">
                                        <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                                        <input name="email" type="email" class="form-control" placeholder="Email" required value='{request.form.get("email", "")}'>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <div class="input-group input-group-lg">
                                        <span class="input-group-text"><i class="fab fa-whatsapp"></i></span>
                                        <input name="whatsapp" class="form-control" placeholder="WhatsApp Number" required value='{request.form.get("whatsapp", "")}'>
                                    </div>
                                </div>
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <select name="gender" class="form-control form-control-lg">
                                            <option value="">Gender</option>
                                            <option value="Male" {"selected" if request.form.get("gender") == "Male" else ""}>Male</option>
                                            <option value="Female" {"selected" if request.form.get("gender") == "Female" else ""}>Female</option>
                                            <option value="Other" {"selected" if request.form.get("gender") == "Other" else ""}>Other</option>
                                        </select>
                                    </div>
                                    <div class="col-6">
                                        <input type="date" name="dob" class="form-control form-control-lg" required value='{request.form.get("dob", "")}'>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <select name="profession" class="form-control form-control-lg">
                                        <option value="">Profession</option>
                                        <option value="Student" {"selected" if request.form.get("profession") == "Student" else ""}>Student</option>
                                        <option value="Business Owner" {"selected" if request.form.get("profession") == "Business Owner" else ""}>Business Owner</option>
                                        <option value="Developer" {"selected" if request.form.get("profession") == "Developer" else ""}>Developer</option>
                                        <option value="Designer" {"selected" if request.form.get("profession") == "Designer" else ""}>Designer</option>
                                        <option value="Freelancer" {"selected" if request.form.get("profession") == "Freelancer" else ""}>Freelancer</option>
                                        <option value="Other" {"selected" if request.form.get("profession") == "Other" else ""}>Other</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <div class="input-group input-group-lg">
                                        <span class="input-group-text"><i class="fas fa-lock"></i></span>
                                        <input type="password" name="password" class="form-control" placeholder="Password" required>
                                    </div>
                                </div>
                                <button class="btn btn-primary btn-lg w-100">
                                    <i class="fas fa-user-plus me-2"></i>Create Account
                                </button>
                                <p class="text-center mt-3">
                                    Already have an account? <a href="/login" class="text-decoration-none fw-bold">Login</a>
                                </p>
                            </form>
                        </div>
                    </div>
                </div>
                """)
            
            hashed_password = bcrypt.generate_password_hash(request.form["password"]).decode('utf-8')
            cur.execute("""INSERT INTO users
            (uid, fullname, email, whatsapp, gender, dob, profession, password, role)
            VALUES(?,?,?,?,?,?,?,?,?)""",(
                str(uuid.uuid4())[:8],
                request.form["fullname"],
                request.form["email"],
                request.form["whatsapp"],
                request.form["gender"],
                request.form["dob"],
                request.form["profession"],
                hashed_password,
                "user"
            ))
            con.commit()
            con.close()
            
            return render_base_template("Signup Success", """
            <div class="auth-container">
                <div class="auth-card">
                    <div class="auth-header">
                        <h3>Account Created!</h3>
                        <p class="mb-0">Welcome to WebCraft Pro</p>
                    </div>
                    <div class="auth-body">
                        <div class="alert alert-success text-center">
                            <i class="fas fa-check-circle fa-3x mb-3"></i>
                            <h4>Registration Successful!</h4>
                            <p>Your account has been created successfully.</p>
                        </div>
                        <a href="/login" class="btn btn-primary btn-lg w-100">
                            <i class="fas fa-sign-in-alt me-2"></i>Login Now
                        </a>
                    </div>
                </div>
            </div>
            """)
            
        except Exception as e:
            con.close()
            return render_base_template("Error", f"""
            <div class="auth-container">
                <div class="auth-card">
                    <div class="auth-header">
                        <h3>Error</h3>
                        <p class="mb-0">Something went wrong</p>
                    </div>
                    <div class="auth-body">
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            Error: {str(e)}
                        </div>
                        <a href="/signup" class="btn btn-primary w-100 mt-3">Try Again</a>
                    </div>
                </div>
            </div>
            """)

    return render_base_template("Signup", """
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-header">
                <h3>Create Account</h3>
                <p class="mb-0">Join our community of web enthusiasts</p>
            </div>
            <div class="auth-body">
                <form method="post">
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fas fa-user"></i></span>
                            <input name="fullname" class="form-control" placeholder="Full Name" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                            <input name="email" type="email" class="form-control" placeholder="Email" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fab fa-whatsapp"></i></span>
                            <input name="whatsapp" class="form-control" placeholder="WhatsApp Number" required>
                        </div>
                    </div>
                    <div class="row mb-3">
                        <div class="col-6">
                            <select name="gender" class="form-control form-control-lg">
                                <option value="">Gender</option>
                                <option>Male</option>
                                <option>Female</option>
                                <option>Other</option>
                            </select>
                        </div>
                        <div class="col-6">
                            <input type="date" name="dob" class="form-control form-control-lg" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <select name="profession" class="form-control form-control-lg">
                            <option value="">Profession</option>
                            <option>Student</option>
                            <option>Business Owner</option>
                            <option>Developer</option>
                            <option>Designer</option>
                            <option>Freelancer</option>
                            <option>Other</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fas fa-lock"></i></span>
                            <input type="password" name="password" class="form-control" placeholder="Password" required>
                        </div>
                    </div>
                    <button class="btn btn-primary btn-lg w-100">
                        <i class="fas fa-user-plus me-2"></i>Create Account
                    </button>
                    <p class="text-center mt-3">
                        Already have an account? <a href="/login" class="text-decoration-none fw-bold">Login</a>
                    </p>
                </form>
            </div>
        </div>
    </div>
    """)

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/dashboard")
        
    if request.method=="POST":
        con = db()
        cur = con.cursor()
        cur.execute("SELECT id, password, role, fullname FROM users WHERE email=?", (request.form["email"],))
        u = cur.fetchone()
        con.close()
        
        if u and bcrypt.check_password_hash(u[1], request.form["password"]):
            login_user(User(u[0], request.form["email"], u[2], u[3]))
            session['show_welcome'] = True
            return redirect("/dashboard")
        else:
            return render_base_template("Login", f"""
            <div class="auth-container">
                <div class="auth-card">
                    <div class="auth-header">
                        <h3>Welcome Back</h3>
                        <p class="mb-0">Login to your WebCraft account</p>
                    </div>
                    <div class="auth-body">
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            Invalid email or password. Please try again.
                        </div>
                        <form method="post">
                            <div class="mb-3">
                                <div class="input-group input-group-lg">
                                    <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                                    <input name="email" type="email" class="form-control" placeholder="Email" required value='{request.form.get("email", "")}'>
                                </div>
                            </div>
                            <div class="mb-3">
                                <div class="input-group input-group-lg">
                                    <span class="input-group-text"><i class="fas fa-lock"></i></span>
                                    <input type="password" name="password" class="form-control" placeholder="Password" required>
                                </div>
                            </div>
                            <button class="btn btn-primary btn-lg w-100">
                                <i class="fas fa-sign-in-alt me-2"></i>Login to Dashboard
                            </button>
                            <p class="text-center mt-3">
                                Don't have an account? <a href="/signup" class="text-decoration-none fw-bold">Sign Up</a>
                            </p>
                        </form>
                    </div>
                </div>
            </div>
            """)

    return render_base_template("Login", """
    <div class="auth-container">
        <div class="auth-card">
            <div class="auth-header">
                <h3>Welcome Back</h3>
                <p class="mb-0">Login to your WebCraft account</p>
            </div>
            <div class="auth-body">
                <form method="post">
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fas fa-envelope"></i></span>
                            <input name="email" type="email" class="form-control" placeholder="Email" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <div class="input-group input-group-lg">
                            <span class="input-group-text"><i class="fas fa-lock"></i></span>
                            <input type="password" name="password" class="form-control" placeholder="Password" required>
                        </div>
                    </div>
                    <button class="btn btn-primary btn-lg w-100">
                        <i class="fas fa-sign-in-alt me-2"></i>Login to Dashboard
                    </button>
                    <p class="text-center mt-3">
                        Don't have an account? <a href="/signup" class="text-decoration-none fw-bold">Sign Up</a>
                    </p>
                </form>
            </div>
        </div>
    </div>
    """)

@app.route("/dashboard")
@login_required
def dashboard():
    templates = get_all_templates()
    
    template_cards = ""
    for template in templates:
        id, name, description, category, features_str, original_price, discount_price, has_discount, tag, image_url, preview_url, status, created = template
        
        features = features_str.split(',') if features_str else []
        
        price_html = ""
        if has_discount:
            price_html = f'''
            <div class="template-price">
                <span class="original-price">${original_price}</span>
                <span class="discount-price">${discount_price}</span>
            </div>
            '''
        else:
            price_html = f'''
            <div class="template-price">
                <span class="discount-price">${original_price}</span>
            </div>
            '''
        
        tag_html = f'<div class="template-badge">{tag}</div>' if tag else ""
        
        features_html = "".join([f'<li><i class="fas fa-check"></i> {feature}</li>' for feature in features[:3]])
        
        if image_url and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], image_url)):
            image_html = f'<img src="/static/uploads/{image_url}" alt="{name}">'
        else:
            image_html = f'<i class="fas fa-image fa-3x"></i><p class="mt-2">{name}</p>'
        
        template_cards += f'''
        <div class="template-card">
            <div class="template-image">
                {image_html}
                {tag_html}
                {price_html}
            </div>
            <div class="template-content">
                <h3 class="template-title">{name}</h3>
                <p class="template-description">{description}</p>
                <ul class="template-features">
                    {features_html}
                </ul>
                <div class="template-buttons">
                    <a href="{preview_url}" target="_blank" class="template-button preview-button">
                        <i class="fas fa-eye me-2"></i>Preview Web
                    </a>
                    <a href="/order-template/{id}" class="template-button">
                        <i class="fas fa-shopping-cart me-2"></i>Order Now
                    </a>
                </div>
            </div>
        </div>
        '''
    
    return render_base_template("Dashboard", f'''
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="card mb-4 animate-scale-in">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-8">
                            <h2 class="mb-2">Welcome back, {current_user.fullname or current_user.email}!</h2>
                            <p class="text-muted mb-0">Choose from our professionally designed templates or create a custom website</p>
                        </div>
                        <div class="col-md-4 text-md-end">
                            <a href="/custom-web" class="btn btn-primary btn-lg">
                                <i class="fas fa-magic me-2"></i>Custom Website
                            </a>
                        </div>
                    </div>
                </div>
            </div>
            
            <h3 class="mb-3 animate-slide-up" style="color: #1e293b;">Website Templates</h3>
            <div class="template-grid">
                {template_cards}
            </div>
        </div>
    </div>
    ''')

@app.route("/order-template/<int:template_id>", methods=["GET", "POST"])
@login_required
def order_template(template_id):
    if request.method == "POST":
        return submit_template_order(template_id)
        
    template = get_template_by_id(template_id)
    if not template:
        return "Template not found", 404
    
    id, name, description, category, features_str, original_price, discount_price, has_discount, tag, image_url, preview_url, status, created = template
    
    return render_base_template(f"Order {name}", f'''
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <h2 class="mb-3 animate-slide-up">Order {name} Template</h2>
            <div class="row animate-scale-in" style="animation-delay: 0.2s">
                <div class="col-lg-8">
                    <div class="card mb-3">
                        <div class="card-body">
                            <form method="post" id="orderForm">
                                <input type="hidden" name="template_id" value="{template_id}">
                                <input type="hidden" name="template_name" value="{name}">
                                <input type="hidden" name="price" value="{discount_price if has_discount else original_price}">
                                
                                <div class="mb-4">
                                    <label class="form-label fw-bold">Your Website Name</label>
                                    <input type="text" name="website_name" class="form-control form-control-lg" placeholder="Enter your website name" required>
                                </div>
                                
                                <div class="mb-4">
                                    <label class="form-label fw-bold">Additional Requirements</label>
                                    <textarea name="requirements" class="form-control form-control-lg" rows="4" placeholder="Any specific requirements or customization needed..."></textarea>
                                </div>
                                
                                <div class="card bg-light mb-4">
                                    <div class="card-body">
                                        <h5>Order Summary</h5>
                                        <hr>
                                        <p><strong>Template:</strong> {name}</p>
                                        <p><strong>Price:</strong> ${discount_price if has_discount else original_price}</p>
                                        <p><strong>Delivery:</strong> 5-7 business days</p>
                                    </div>
                                </div>
                                
                                <button type="submit" class="btn btn-primary btn-lg w-100 animate-glow">
                                    <i class="fas fa-check-circle me-2"></i>Confirm Order
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-4">
                    <div class="card order-summary-card">
                        <div class="card-body">
                            <h5 class="mb-3">Order Details</h5>
                            <div class="mb-4">
                                <p class="mb-1"><strong>Template Type:</strong></p>
                                <p class="fw-bold text-primary">{name}</p>
                            </div>
                            <div class="mb-4">
                                <p class="mb-1"><strong>Pricing:</strong></p>
                                {f'<p class="text-decoration-line-through text-muted mb-1">${original_price}</p><p class="fs-3 fw-bold text-success mb-0">${discount_price}</p>' if has_discount else f'<p class="fs-3 fw-bold text-success mb-0">${original_price}</p>'}
                            </div>
                            <div>
                                <h6 class="mb-3">What's Included:</h6>
                                <ul class="list-unstyled">
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> Responsive Design</li>
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> Basic SEO Setup</li>
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> 1 Year Hosting</li>
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> Technical Support</li>
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> Mobile Optimization</li>
                                    <li class="mb-2"><i class="fas fa-check-circle text-success me-2"></i> Fast Loading Speed</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    ''')

def submit_template_order(template_id):
    template = get_template_by_id(template_id)
    if not template:
        return "Template not found", 404
    
    order_id = "TMP-" + str(uuid.uuid4())[:8]
    con = db()
    cur = con.cursor()
    
    try:
        cur.execute("""INSERT INTO orders 
        (order_id, user_id, website_type, budget, stage, status, order_type, website_name, requirements) 
        VALUES(?,?,?,?,?,?,?,?,?)""", (
            order_id,
            current_user.id,
            template[1],  # template name
            template[6] if template[7] else template[5],  # discount price if available, else original price
            "Template Selected",
            "Pending",
            "template",
            request.form.get("website_name", ""),
            request.form.get("requirements", "")
        ))
        
        con.commit()
        con.close()
        
        return redirect("/orders")
    except Exception as e:
        con.close()
        return f"Error: {str(e)}", 400

@app.route("/custom-web")
@login_required
def custom_web():
    questions = [
        "Hello! I'm Hydro, the assistant of Arafat. I'm here to understand your requirements better. 😊 To begin with, what type of website are you looking for? (For example: E-commerce, Portfolio, Business, Blog, etc.)",
        
        "Great choice! May I know your brand or business name?",
        
        "Do you already have a logo for your brand, or would you like us to design one for you?",
        
        "If you have a logo, is it final or are you open to improvements?",
        
        "What is the main purpose of this website? (For example: selling products, building trust, getting leads, or sharing information)",
        
        "That sounds wonderful! I wish you great success with your business. 🌱",
        
        "Now, could you please describe your website idea in simple English? You may explain everything from A to Z.",
        
        "Thank you for sharing. Do you prefer a modern, simple design or a premium, luxurious look?",
        
        "What is your timeline and urgency level for this project?",
        
        "Do you need ongoing maintenance and future updates after the website is completed?",
        
        "Who is your target audience for this website?",
        
        "Is mobile responsiveness a priority for your website?",
        
        "What language preference do you have for the website?",
        
        "Do you have any SEO or digital marketing expectations?",
        
        "Is there anything specific you really like or dislike in websites you've seen before?",
        
        "Do you have any reference websites that inspire you? If yes, please share the links.",
        
        "Please share your social media links (such as Facebook, Instagram, or LinkedIn) so we can connect them with your website.",
        
        "Kindly provide an email address or WhatsApp number so we can easily contact you for updates and handover.",
        
        "Just to confirm, is all the information you provided correct?",
        
        "Perfect! One more small question, if you don't mind 😊",
        
        "Please don't say no right away—just answer this one question for me. What is your budget? I'll plan and work according to your budget.",
        
        "Thank you for your honesty. We truly appreciate it.",
        
        "Arafat will start planning your website based on your requirements. You're in good hands—no worries at all.",
        
        "If you have any questions later, feel free to message us anytime at wa.me/8801610709657",
    ]
    
    questions_js = json.dumps(questions)
    
    return render_base_template("Custom Website", f'''
    <div class="chat-wrapper animate-scale-in">
        <div class="chat-header">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h4 class="mb-1">Custom Website Consultation</h4>
                    <p class="mb-0">Ask me anything about your website requirements</p>
                </div>
                <div class="progress-container" style="width: 200px;">
                    <div class="progress-bar" id="progressBar" style="width: 4%"></div>
                </div>
            </div>
        </div>
        
        <div class="chat-messages" id="messagesArea">
            <div class="chat-message bot-message">
                <p id="currentQuestion">{questions[0]}</p>
            </div>
        </div>
        
        <div class="chat-input-wrapper">
            <div class="flex-grow-1">
                <textarea class="chat-input" id="userAnswer" rows="1" placeholder="Type your answer here..."></textarea>
            </div>
            <div class="d-flex gap-2">
                <button class="btn btn-outline-secondary" onclick="prevQuestion()" id="prevBtn" style="display: none;">
                    <i class="fas fa-arrow-left"></i>
                </button>
                <button class="chat-send-btn" onclick="nextQuestion()" id="nextBtn">
                    <i class="fas fa-arrow-right"></i>
                </button>
            </div>
        </div>
        
        <div id="orderButtons" class="chat-input-wrapper" style="display: none;">
            <div class="w-100 text-center">
                <h5 class="mb-3">Ready to place your order?</h5>
                <div class="d-flex justify-content-center gap-3">
                    <button class="btn btn-success btn-lg" onclick="placeOrder()">
                        <i class="fas fa-check-circle me-2"></i>Place Order
                    </button>
                    <button class="btn btn-outline-danger btn-lg" onclick="resetQuestions()">
                        <i class="fas fa-times-circle me-2"></i>Start Over
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const questions = {questions_js};
        let currentQuestionIndex = 0;
        const answers = [];
        
        function updateProgress() {{
            const progress = ((currentQuestionIndex + 1) / questions.length) * 100;
            document.getElementById('progressBar').style.width = progress + '%';
            
            // Show/hide previous button
            document.getElementById('prevBtn').style.display = currentQuestionIndex > 0 ? 'block' : 'none';
        }}
        
        function addMessage(message, isUser = false) {{
            const messagesArea = document.getElementById('messagesArea');
            const messageDiv = document.createElement('div');
            messageDiv.className = isUser ? 'chat-message user-message' : 'chat-message bot-message';
            messageDiv.innerHTML = '<p class="mb-0">' + message + '</p>';
            messagesArea.appendChild(messageDiv);
            
            // Scroll to bottom
            messagesArea.scrollTo({{
                top: messagesArea.scrollHeight,
                behavior: 'smooth'
            }});
        }}
        
        function nextQuestion() {{
            const answerText = document.getElementById('userAnswer').value.trim();
            if (!answerText && currentQuestionIndex < questions.length - 1) {{
                showNotification('warning', 'Empty Answer', 'Please provide an answer');
                return;
            }}
            
            // Add user message if there's text
            if (answerText) {{
                addMessage(answerText, true);
            }}
            
            answers[currentQuestionIndex] = answerText;
            
            if (currentQuestionIndex < questions.length - 1) {{
                currentQuestionIndex++;
                
                // Add bot message
                addMessage(questions[currentQuestionIndex]);
                
                // Clear input and update
                document.getElementById('userAnswer').value = answers[currentQuestionIndex] || '';
                updateProgress();
                
                // Auto focus
                document.getElementById('userAnswer').focus();
                
                // Show order buttons on last question
                if (currentQuestionIndex === questions.length - 1) {{
                    document.querySelector('.chat-input-wrapper').style.display = 'none';
                    document.getElementById('orderButtons').style.display = 'block';
                }}
            }}
            
            // Auto resize textarea
            const textarea = document.getElementById('userAnswer');
            textarea.style.height = 'auto';
            textarea.style.height = (textarea.scrollHeight) + 'px';
        }}
        
        function prevQuestion() {{
            if (currentQuestionIndex > 0) {{
                answers[currentQuestionIndex] = document.getElementById('userAnswer').value;
                currentQuestionIndex--;
                
                // Remove last two messages
                const messagesArea = document.getElementById('messagesArea');
                messagesArea.removeChild(messagesArea.lastChild);
                if (answers[currentQuestionIndex + 1]) {{
                    messagesArea.removeChild(messagesArea.lastChild);
                }}
                
                // Update input and progress
                document.getElementById('userAnswer').value = answers[currentQuestionIndex] || '';
                updateProgress();
                
                // Hide order buttons
                document.querySelector('.chat-input-wrapper').style.display = 'flex';
                document.getElementById('orderButtons').style.display = 'none';
            }}
        }}
        
        function resetQuestions() {{
            if (confirm('Are you sure you want to start over? All your answers will be lost.')) {{
                currentQuestionIndex = 0;
                answers.length = 0;
                document.getElementById('messagesArea').innerHTML = '<div class="chat-message bot-message"><p id="currentQuestion">' + questions[0] + '</p></div>';
                document.getElementById('userAnswer').value = '';
                document.querySelector('.chat-input-wrapper').style.display = 'flex';
                document.getElementById('orderButtons').style.display = 'none';
                updateProgress();
                
                showNotification('info', 'Reset Complete', 'You can start answering questions again');
            }}
        }}
        
        function placeOrder() {{
            const finalAnswer = document.getElementById('userAnswer').value.trim();
            if (!finalAnswer) {{
                showNotification('warning', 'Empty Answer', 'Please answer the last question');
                return;
            }}
            
            answers[currentQuestionIndex] = finalAnswer;
            
            // Show loading
            showNotification('info', 'Processing', 'Placing your order...');
            
            fetch('/submit-custom-order', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    answers: answers,
                    questions: questions
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    showNotification('success', 'Order Placed', 'Your custom website order has been placed successfully!');
                    setTimeout(() => {{
                        window.location.href = '/orders';
                    }}, 2000);
                }} else {{
                    showNotification('error', 'Order Failed', 'Error placing order: ' + data.error);
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                showNotification('error', 'Network Error', 'Failed to place order. Please try again.');
            }});
        }}
        
        // Initialize
        updateProgress();
        
        // Enter key to submit
        document.getElementById('userAnswer').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                nextQuestion();
            }}
        }});
        
        // Auto resize textarea
        const textarea = document.getElementById('userAnswer');
        textarea.addEventListener('input', function() {{
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        }});
        
        // Focus on input
        setTimeout(() => {{
            textarea.focus();
        }}, 500);
    </script>
    ''')

@app.route("/submit-custom-order", methods=["POST"])
@login_required
def submit_custom_order():
    try:
        data = request.get_json()
        order_id = "CUST-" + str(uuid.uuid4())[:8]
        
        con = db()
        cur = con.cursor()
        
        # Get user's WhatsApp from database
        cur.execute("SELECT whatsapp FROM users WHERE id=?", (current_user.id,))
        user_data = cur.fetchone()
        whatsapp = user_data[0] if user_data else ""
        
        # Extract budget from answers (question 20 is about budget)
        answers = data.get('answers', [])
        budget = "Not specified"
        if len(answers) > 20 and answers[20]:
            budget = answers[20]
        
        # Extract website name from first answers
        website_name = answers[1] if len(answers) > 1 else ""
        
        # Create requirements summary
        requirements = "Custom website requirements collected through consultation."
        
        cur.execute("""INSERT INTO orders 
        (order_id, user_id, website_type, answers, budget, stage, status, order_type, website_name, requirements) 
        VALUES(?,?,?,?,?,?,?,?,?,?)""", (
            order_id,
            current_user.id,
            "Custom Website",
            json.dumps(data),
            budget,
            "Requirement Analysis",
            "Pending",
            "custom",
            website_name,
            requirements
        ))
        
        con.commit()
        con.close()
        
        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/orders")
@login_required
def orders():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT order_id, website_type, stage, status, created, folder_submitted FROM orders WHERE user_id=? ORDER BY id DESC", (current_user.id,))
    rows = cur.fetchall()
    con.close()
    
    unread_orders_count = get_unread_orders_count(current_user.id)
    
    if not rows:
        return render_base_template("My Orders", """
        <div class="content-wrapper">
            <div style="padding: 40px 20px; text-align: center;">
                <i class="fas fa-box-open fa-4x text-muted mb-4 animate-pulse"></i>
                <h3 class="mb-3">No Orders Yet</h3>
                <p class="text-muted mb-4">You haven't placed any orders yet.</p>
                <a href="/dashboard" class="btn btn-primary btn-lg">
                    <i class="fas fa-shopping-cart me-2"></i>Browse Templates
                </a>
            </div>
        </div>
        """, unread_orders_count=unread_orders_count)
    
    orders_html = ""
    for order in rows:
        order_id, website_type, stage, status, created, folder_submitted = order
        status_color = "success" if status == "Granted" else "warning" if status == "Pending" else "info"
        
        # Check for unread notifications for this order
        con_temp = db()
        cur_temp = con_temp.cursor()
        cur_temp.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND message LIKE ? AND is_read=0", 
                        (current_user.id, f"%{order_id}%"))
        order_unread = cur_temp.fetchone()[0]
        
        # Check if folder is submitted
        folder_badge = ""
        if folder_submitted == 1:
            folder_badge = '<span class="badge bg-success ms-2"><i class="fas fa-folder me-1"></i>Ready</span>'
        else:
            folder_badge = '<span class="badge bg-secondary ms-2"><i class="fas fa-clock me-1"></i>Pending</span>'
        
        orders_html += f"""
        <div class="card mb-3 animate-slide-up">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h5 class="card-title mb-1">{order_id} {folder_badge}</h5>
                        <p class="text-muted mb-1">{website_type} • {created}</p>
                        <span class="badge bg-{status_color}">{status}</span>
                        <span class="badge bg-secondary ms-2">{stage}</span>
                        {"<span class='badge bg-danger ms-2'><i class='fas fa-bell'></i></span>" if order_unread > 0 else ""}
                    </div>
                    <div>
                        <a href="/order-details/{order_id}" class="btn btn-outline-primary btn-sm">
                            <i class="fas fa-eye me-1"></i>View
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """
        con_temp.close()
    
    return render_base_template("My Orders", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">My Orders</h2>
                <a href="/your-web" class="btn btn-success btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-download me-2"></i>Your Web
                </a>
            </div>
            {orders_html}
        </div>
    </div>
    """, unread_orders_count=unread_orders_count)

@app.route("/order-details/<order_id>")
@login_required
def order_details(order_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM orders WHERE order_id=? AND user_id=?", (order_id, current_user.id))
    order = cur.fetchone()
    
    if not order:
        con.close()
        return "Order not found", 404
    
    # Get messages for this order
    cur.execute("SELECT * FROM messages WHERE order_id=? ORDER BY created", (order[0],))
    messages = cur.fetchall()
    
    # Mark notifications for this order as read
    cur.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND message LIKE ?", 
                (current_user.id, f"%{order_id}%"))
    
    con.commit()
    con.close()
    
    messages_html = ""
    for msg in messages:
        msg_class = "user-message" if msg[4] == "user" else "bot-message"
        sender_name = "You" if msg[4] == "user" else "Admin"
        messages_html += f"""
        <div class="chat-message {msg_class}">
            <small class="text-muted">{sender_name} • {msg[5]}</small>
            <p class="mb-0">{msg[3]}</p>
        </div>
        """
    
    order_status = order[7]  # status column
    chat_enabled = order_status == "Granted"
    
    return render_base_template(f"Order {order_id}", f'''
    <div class="chat-wrapper animate-scale-in">
        <div class="chat-header">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h4 class="mb-0">Order: {order_id}</h4>
                    <p class="text-muted mb-0">Status: {order[7]} | Stage: {order[6]}</p>
                </div>
                <a href="/orders" class="btn btn-outline-primary btn-sm">
                    <i class="fas fa-arrow-left me-1"></i>Back
                </a>
            </div>
        </div>
        
        <div class="chat-messages" id="messagesArea">
            {messages_html if messages_html else '<div class="text-center text-muted" style="padding: 40px;"><i class="fas fa-comments fa-3x mb-3"></i><p>No messages yet</p></div>'}
        </div>
        
        {f'''<div class="chat-input-wrapper">
            <form method="post" action="/send-message/{order_id}">
                <div class="input-group">
                    <input type="text" name="message" class="form-control chat-input" placeholder="Type your message..." required>
                    <button class="chat-send-btn" type="submit">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </form>
        </div>''' if chat_enabled else '''<div class="chat-input-wrapper">
            <div class="notification info" style="position: relative; margin: 0;">
                <div class="notification-icon">
                    <i class="fas fa-info-circle"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">Chat Disabled</div>
                    <div class="notification-message">Chat will be enabled when the order status is marked as "Granted" by admin.</div>
                </div>
            </div>
        </div>'''}
    </div>
    ''')

@app.route("/send-message/<order_id>", methods=["POST"])
@login_required
def send_message(order_id):
    message = request.form.get("message", "").strip()
    if not message:
        return redirect(f"/order-details/{order_id}")
    
    con = db()
    cur = con.cursor()
    
    # Get order id from order_id
    cur.execute("SELECT id FROM orders WHERE order_id=? AND user_id=?", (order_id, current_user.id))
    order_row = cur.fetchone()
    
    if order_row:
        order_db_id = order_row[0]
        cur.execute("""INSERT INTO messages (order_id, user_id, message, sender) 
                      VALUES(?,?,?,?)""", 
                    (order_db_id, current_user.id, message, "user"))
        con.commit()
    
    con.close()
    return redirect(f"/order-details/{order_id}")

@app.route("/account")
@login_required
def account():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT fullname, email, whatsapp, gender, dob, profession FROM users WHERE id=?", (current_user.id,))
    user_data = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (current_user.id,))
    order_count = cur.fetchone()[0]
    
    # Get unread notifications
    unread_notifications = get_unread_notifications_count(current_user.id)
    
    # Get completed websites count
    completed_websites = get_completed_websites_count(current_user.id)
    
    con.close()
    
    # Create badge for unread notifications
    notification_badge = ""
    if unread_notifications > 0:
        notification_badge = f"""
        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">
            {unread_notifications}
        </span>
        """
    
    return render_base_template("My Account", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <h2 class="mb-3 animate-slide-up">My Account</h2>
            
            <div class="row">
                <div class="col-md-4 mb-3">
                    <div class="card animate-scale-in">
                        <div class="card-body text-center">
                            <div class="mb-3">
                                <i class="fas fa-user-circle fa-4x text-primary animate-pulse"></i>
                            </div>
                            <h4>{user_data[0]}</h4>
                            <p class="text-muted">{user_data[1]}</p>
                            <p class="badge bg-primary">{current_user.role.upper()}</p>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-8">
                    <div class="card mb-3 animate-scale-in" style="animation-delay: 0.1s">
                        <div class="card-body">
                            <h5>Profile Information</h5>
                            <hr>
                            
                            <div class="row mb-3">
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">Full Name</label>
                                    <input type="text" class="form-control" value="{user_data[0]}" readonly>
                                </div>
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">Email</label>
                                    <input type="text" class="form-control" value="{user_data[1]}" readonly>
                                </div>
                            </div>
                            
                            <div class="row mb-3">
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">WhatsApp</label>
                                    <input type="text" class="form-control" value="{user_data[2]}" readonly>
                                </div>
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">Gender</label>
                                    <input type="text" class="form-control" value="{user_data[3]}" readonly>
                                </div>
                            </div>
                            
                            <div class="row mb-3">
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">Date of Birth</label>
                                    <input type="text" class="form-control" value="{user_data[4]}" readonly>
                                </div>
                                <div class="col-md-6 mb-2">
                                    <label class="form-label">Profession</label>
                                    <input type="text" class="form-control" value="{user_data[5]}" readonly>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card animate-scale-in" style="animation-delay: 0.2s">
                        <div class="card-body">
                            <h5>Quick Stats</h5>
                            <hr>
                            <div class="row">
                                <div class="col-6">
                                    <div class="text-center">
                                        <div class="display-6 fw-bold">{order_count}</div>
                                        <p class="text-muted mb-0">Total Orders</p>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="text-center">
                                        <div class="display-6 fw-bold">{completed_websites}</div>
                                        <p class="text-muted mb-0">Ready Websites</p>
                                    </div>
                                </div>
                            </div>
                            <div class="mt-3">
                                <a href="/orders" class="btn btn-primary me-2">
                                    <i class="fas fa-shopping-cart me-1"></i>View Orders
                                </a>
                                <a href="/your-web" class="btn btn-success me-2">
                                    <i class="fas fa-download me-1"></i>Your Web
                                </a>
                                <a href="/notifications" class="btn btn-outline-primary position-relative">
                                    <i class="fas fa-bell me-1"></i>Notifications
                                    {notification_badge}
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/your-web")
@login_required
def your_web():
    con = db()
    cur = con.cursor()
    
    # Get orders where folder is submitted
    cur.execute("""
        SELECT order_id, website_type, website_name, folder_submitted_at 
        FROM orders 
        WHERE user_id=? AND folder_submitted=1 
        ORDER BY folder_submitted_at DESC
    """, (current_user.id,))
    
    completed_websites = cur.fetchall()
    
    con.close()
    
    if not completed_websites:
        return render_base_template("Your Web", """
        <div class="content-wrapper">
            <div style="padding: 40px 20px; text-align: center;">
                <i class="fas fa-cloud-download-alt fa-4x text-muted mb-4 animate-pulse"></i>
                <h3 class="mb-3">No Websites Ready</h3>
                <p class="text-muted mb-4">Your completed websites will appear here once they're ready for download.</p>
                <a href="/dashboard" class="btn btn-primary btn-lg">
                    <i class="fas fa-shopping-cart me-2"></i>Browse Templates
                </a>
            </div>
        </div>
        """)
    
    websites_html = ""
    for website in completed_websites:
        order_id, website_type, website_name, submitted_at = website
        
        websites_html += f"""
        <div class="card mb-3 animate-scale-in">
            <div class="card-body">
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <h5 class="card-title">{website_name or order_id}</h5>
                        <p class="text-muted mb-1">
                            <i class="fas fa-tag me-2"></i>{website_type}
                            <span class="ms-3"><i class="far fa-calendar me-2"></i>{submitted_at}</span>
                        </p>
                    </div>
                    <div class="col-md-4 text-md-end">
                        <a href="/download-website/{order_id}" class="btn btn-success">
                            <i class="fas fa-download me-2"></i>Download Website
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """
    
    return render_base_template("Your Web", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Your Websites</h2>
                <a href="/orders" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back to Orders
                </a>
            </div>
            
            <div class="alert alert-success animate-scale-in" style="animation-delay: 0.2s">
                <i class="fas fa-check-circle me-2"></i>
                You have {len(completed_websites)} completed website(s) ready for download
            </div>
            
            {websites_html}
        </div>
    </div>
    """)

@app.route("/download-website/<order_id>")
@login_required
def download_website(order_id):
    # Check if order belongs to user and folder is submitted
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, website_name FROM orders WHERE order_id=? AND user_id=? AND folder_submitted=1", 
                (order_id, current_user.id))
    order = cur.fetchone()
    
    if not order:
        con.close()
        return "Website not found or not ready", 404
    
    order_id_db, website_name = order
    
    # Check if website folder exists
    website_folder = os.path.join(app.config['WEBSITE_FOLDER'], str(order_id_db))
    
    if not os.path.exists(website_folder):
        # Create a sample index.html if folder doesn't exist
        os.makedirs(website_folder, exist_ok=True)
        sample_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{website_name or 'Your Website'}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #333; border-bottom: 2px solid #4361ee; padding-bottom: 10px; }}
                .info {{ background: #e8f4fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{website_name or 'Your Website'}</h1>
                <div class="info">
                    <p><strong>Order ID:</strong> {order_id}</p>
                    <p><strong>Status:</strong> Ready for deployment</p>
                    <p><strong>Download Date:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <p>This is your completed website folder. Upload these files to your hosting provider.</p>
                <p>For assistance with deployment, contact our support team.</p>
            </div>
        </body>
        </html>
        """
        
        with open(os.path.join(website_folder, 'index.html'), 'w') as f:
            f.write(sample_html)
    
    # Create zip file
    zip_filename = f"{order_id}_website.zip"
    zip_path = os.path.join(app.config['WEBSITE_FOLDER'], zip_filename)
    
    # Create zip file
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(website_folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, website_folder)
                zipf.write(file_path, arcname)
    
    con.close()
    
    # Send the zip file
    return send_file(zip_path, as_attachment=True, download_name=zip_filename)

@app.route("/notifications")
@login_required
def notifications():
    con = db()
    cur = con.cursor()
    
    cur.execute("SELECT message, created, is_read FROM notifications WHERE user_id=? ORDER BY created DESC", (current_user.id,))
    rows = cur.fetchall()
    
    # Mark as read
    cur.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (current_user.id,))
    con.commit()
    con.close()
    
    if not rows:
        return render_base_template("Notifications", """
        <div class="content-wrapper">
            <div style="padding: 40px 20px; text-align: center;">
                <i class="fas fa-bell-slash fa-4x text-muted mb-4 animate-pulse"></i>
                <h3 class="mb-3">No Notifications</h3>
                <p class="text-muted">You don't have any notifications yet.</p>
            </div>
        </div>
        """)
    
    notifications_html = ""
    for notification in rows:
        message, created, is_read = notification
        read_class = "" if is_read else "border-start border-3 border-primary"
        read_badge = '<span class="badge bg-danger ms-2">NEW</span>' if not is_read else ""
        notifications_html += f"""
        <div class="card mb-2 {read_class} animate-slide-up">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div style="flex: 1;">
                        <p class="mb-1">{message}</p>
                        <small class="text-muted">{created}</small>
                    </div>
                    {read_badge}
                </div>
            </div>
        </div>
        """
    
    return render_base_template("Notifications", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Notifications</h2>
                <a href="/account" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            {notifications_html}
        </div>
    </div>
    """)

# ---------------- ADMIN FOLDER SUBMISSION ----------------
@app.route("/admin/submit-folder", methods=["GET", "POST"])
@login_required
def admin_submit_folder():
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    
    if request.method == "POST":
        order_id = request.form.get("order_id")
        folder = request.files.get("folder")
        
        if not order_id or not folder:
            return "Please select an order and upload a folder", 400
        
        # Get order details
        cur.execute("SELECT id, user_id, website_name FROM orders WHERE order_id=?", (order_id,))
        order = cur.fetchone()
        
        if not order:
            return "Order not found", 404
        
        order_db_id, user_id, website_name = order
        
        # Create folder for website
        website_folder = os.path.join(app.config['WEBSITE_FOLDER'], str(order_db_id))
        os.makedirs(website_folder, exist_ok=True)
        
        # Save uploaded files
        if folder.filename:
            filename = secure_filename(folder.filename)
            file_path = os.path.join(website_folder, filename)
            folder.save(file_path)
            
            # If it's a zip file, extract it
            if filename.endswith('.zip'):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(website_folder)
                os.remove(file_path)  # Remove the zip file after extraction
        
        # Update order
        cur.execute("UPDATE orders SET folder_submitted=1, folder_submitted_at=? WHERE id=?", 
                   (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), order_db_id))
        
        # Add notification for user
        notification_msg = f"Your website folder for order {order_id} has been submitted and is ready for download!"
        cur.execute("INSERT INTO notifications(user_id, message, sender_id) VALUES(?,?,?)",
                   (user_id, notification_msg, current_user.id))
        
        con.commit()
        con.close()
        
        return redirect("/admin/submit-folder?success=1")
    
    # Get all orders
    cur.execute("""
        SELECT o.order_id, o.website_type, o.website_name, o.created, u.fullname, o.folder_submitted 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        WHERE o.status='Granted' 
        ORDER BY o.id DESC
    """)
    orders = cur.fetchall()
    con.close()
    
    success_msg = ""
    if request.args.get('success'):
        success_msg = """
        <div class="alert alert-success animate-scale-in">
            <i class="fas fa-check-circle me-2"></i>
            Website folder submitted successfully!
        </div>
        """
    
    orders_html = ""
    for order in orders:
        order_id, website_type, website_name, created, fullname, folder_submitted = order
        folder_badge = "bg-success" if folder_submitted == 1 else "bg-warning"
        folder_text = "Submitted" if folder_submitted == 1 else "Pending"
        
        orders_html += f"""
        <tr class="animate-slide-up">
            <td>
                <strong>{order_id}</strong><br>
                <small class="text-muted">{fullname}</small>
            </td>
            <td>{website_type}</td>
            <td>{website_name or 'N/A'}</td>
            <td>{created}</td>
            <td><span class="badge {folder_badge}">{folder_text}</span></td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="selectOrder('{order_id}', '{website_name or order_id}')">
                    <i class="fas fa-upload me-1"></i>Select
                </button>
            </td>
        </tr>
        """
    
    return render_base_template("Submit Website Folder", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Submit Website Folder</h2>
                <a href="/admin" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            
            {success_msg}
            
            <div class="row">
                <div class="col-md-5 mb-3">
                    <div class="card animate-scale-in" style="animation-delay: 0.2s">
                        <div class="card-body">
                            <h5>Submit Folder</h5>
                            <hr>
                            <form method="post" enctype="multipart/form-data" id="submitForm">
                                <div class="mb-3">
                                    <label class="form-label">Selected Order</label>
                                    <input type="text" id="selectedOrder" class="form-control" readonly required>
                                    <input type="hidden" name="order_id" id="orderIdInput">
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Website Folder (ZIP file)</label>
                                    <input type="file" name="folder" class="form-control" accept=".zip,.rar,.7z" required>
                                    <small class="text-muted">Upload the completed website as a ZIP file</small>
                                </div>
                                
                                <button type="submit" class="btn btn-success w-100 animate-glow">
                                    <i class="fas fa-upload me-2"></i>Submit Folder
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-7">
                    <div class="card animate-scale-in" style="animation-delay: 0.3s">
                        <div class="card-body">
                            <h5>Available Orders</h5>
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>Order/Customer</th>
                                            <th>Type</th>
                                            <th>Website Name</th>
                                            <th>Created</th>
                                            <th>Status</th>
                                            <th>Action</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {orders_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function selectOrder(orderId, websiteName) {{
            document.getElementById('selectedOrder').value = orderId + ' - ' + websiteName;
            document.getElementById('orderIdInput').value = orderId;
            showNotification('success', 'Order Selected', 'Order ' + orderId + ' selected for folder submission');
        }}
        
        // Auto select from URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const orderParam = urlParams.get('order');
        if (orderParam) {{
            document.getElementById('selectedOrder').value = orderParam;
            document.getElementById('orderIdInput').value = orderParam;
        }}
    </script>
    """)

# ---------------- ADMIN TEMPLATE MANAGEMENT ----------------
@app.route("/admin/templates")
@login_required
def admin_templates():
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM templates ORDER BY id DESC")
    templates = cur.fetchall()
    con.close()
    
    templates_html = ""
    for template in templates:
        id, name, description, category, features_str, original_price, discount_price, has_discount, tag, image_url, preview_url, status, created = template
        
        features = features_str.split(',')[:3] if features_str else []
        features_html = ", ".join(features)
        
        status_badge = "success" if status == 1 else "danger"
        status_text = "Active" if status == 1 else "Inactive"
        
        if image_url and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], image_url)):
            image_preview = f'<img src="/static/uploads/{image_url}" class="image-preview" alt="{name}">'
        else:
            image_preview = '<i class="fas fa-image text-muted"></i>'
        
        templates_html += f"""
        <tr class="animate-slide-up">
            <td>{id}</td>
            <td>{name}</td>
            <td>{category}</td>
            <td>${original_price}</td>
            <td>${discount_price if has_discount else original_price}</td>
            <td>{features_html}</td>
            <td>{image_preview}</td>
            <td><span class="badge bg-{status_badge}">{status_text}</span></td>
            <td>{created[:10] if created else 'N/A'}</td>
            <td>
                <div class="action-buttons">
                    <a href="/admin/edit-template/{id}" class="btn btn-sm btn-warning">
                        <i class="fas fa-edit"></i>
                    </a>
                    <a href="/admin/delete-template/{id}" class="btn btn-sm btn-danger" onclick="return confirm('Are you sure you want to delete this template?')">
                        <i class="fas fa-trash"></i>
                    </a>
                </div>
            </td>
        </tr>
        """
    
    return render_base_template("Manage Templates", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Manage Templates</h2>
                <div>
                    <a href="/admin" class="btn btn-outline-primary btn-sm me-2 animate-slide-up" style="animation-delay: 0.1s">
                        <i class="fas fa-arrow-left me-2"></i>Back
                    </a>
                    <a href="/admin/add-template" class="btn btn-primary btn-sm animate-slide-up" style="animation-delay: 0.2s">
                        <i class="fas fa-plus me-2"></i>Add New Template
                    </a>
                </div>
            </div>
            
            <div class="card animate-scale-in" style="animation-delay: 0.3s">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="admin-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Name</th>
                                    <th>Category</th>
                                    <th>Original Price</th>
                                    <th>Discount Price</th>
                                    <th>Features</th>
                                    <th>Image</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {templates_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/add-template", methods=["GET", "POST"])
@login_required
def admin_add_template():
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    if request.method == "POST":
        try:
            name = request.form.get("name")
            description = request.form.get("description")
            category = request.form.get("category")
            features = request.form.get("features")
            original_price = float(request.form.get("original_price", 0))
            discount_price = float(request.form.get("discount_price", 0))
            has_discount = 1 if request.form.get("has_discount") == "on" else 0
            tag = request.form.get("tag", "")
            preview_url = request.form.get("preview_url", "")
            
            # Handle file upload
            image_url = ""
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = filename
            
            con = db()
            cur = con.cursor()
            cur.execute("""INSERT INTO templates 
            (name, description, category, features, original_price, discount_price, has_discount, tag, image_url, preview_url, status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", 
            (name, description, category, features, original_price, discount_price, has_discount, tag, image_url, preview_url, 1))
            
            con.commit()
            con.close()
            
            return redirect("/admin/templates")
        except Exception as e:
            return f"Error: {str(e)}", 400
    
    return render_base_template("Add Template", """
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Add New Template</h2>
                <a href="/admin/templates" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            
            <div class="card animate-scale-in" style="animation-delay: 0.2s">
                <div class="card-body">
                    <form method="post" enctype="multipart/form-data">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Template Name</label>
                                    <input type="text" name="name" class="form-control" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Category</label>
                                    <input type="text" name="category" class="form-control" required>
                                </div>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Description</label>
                            <textarea name="description" class="form-control" rows="3" required></textarea>
                        </div>
                        
                        <div class="form-group">
                            <label>Features (comma separated)</label>
                            <textarea name="features" class="form-control" rows="3" placeholder="Feature 1, Feature 2, Feature 3, ..." required></textarea>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-4">
                                <div class="form-group">
                                    <label>Original Price ($)</label>
                                    <input type="number" step="0.01" name="original_price" class="form-control" required>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="form-group">
                                    <label>Discount Price ($)</label>
                                    <input type="number" step="0.01" name="discount_price" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="form-group">
                                    <div class="form-check mt-4">
                                        <input type="checkbox" name="has_discount" class="form-check-input" id="hasDiscount">
                                        <label class="form-check-label" for="hasDiscount">Has Discount</label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Tag (optional)</label>
                                    <input type="text" name="tag" class="form-control" placeholder="e.g., Popular, Recommended, Best Value">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Preview URL</label>
                                    <input type="url" name="preview_url" class="form-control" placeholder="https://demo.example.com">
                                </div>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Template Image</label>
                            <input type="file" name="image" class="form-control" accept="image/*">
                            <small class="text-muted">Upload an image for the template (optional)</small>
                        </div>
                        
                        <button type="submit" class="btn btn-primary btn-lg w-100 animate-glow">
                            <i class="fas fa-save me-2"></i>Save Template
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/edit-template/<int:template_id>", methods=["GET", "POST"])
@login_required
def admin_edit_template(template_id):
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    template = get_template_by_id(template_id)
    if not template:
        return "Template not found", 404
    
    if request.method == "POST":
        try:
            name = request.form.get("name")
            description = request.form.get("description")
            category = request.form.get("category")
            features = request.form.get("features")
            original_price = float(request.form.get("original_price", 0))
            discount_price = float(request.form.get("discount_price", 0))
            has_discount = 1 if request.form.get("has_discount") == "on" else 0
            tag = request.form.get("tag", "")
            preview_url = request.form.get("preview_url", "")
            status = 1 if request.form.get("status") == "on" else 0
            
            # Handle file upload
            image_url = template[9]  # Keep existing image
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    # Delete old image if exists
                    if image_url and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], image_url)):
                        try:
                            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image_url))
                        except:
                            pass
                    
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_url = filename
            
            con = db()
            cur = con.cursor()
            cur.execute("""UPDATE templates SET 
            name=?, description=?, category=?, features=?, original_price=?, discount_price=?, 
            has_discount=?, tag=?, image_url=?, preview_url=?, status=? WHERE id=?""", 
            (name, description, category, features, original_price, discount_price, 
             has_discount, tag, image_url, preview_url, status, template_id))
            
            con.commit()
            con.close()
            
            return redirect("/admin/templates")
        except Exception as e:
            return f"Error: {str(e)}", 400
    
    id, name, description, category, features_str, original_price, discount_price, has_discount, tag, image_url, preview_url, status, created = template
    
    return render_base_template("Edit Template", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Edit Template</h2>
                <a href="/admin/templates" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            
            <div class="card animate-scale-in" style="animation-delay: 0.2s">
                <div class="card-body">
                    <form method="post" enctype="multipart/form-data">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Template Name</label>
                                    <input type="text" name="name" class="form-control" value="{name}" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Category</label>
                                    <input type="text" name="category" class="form-control" value="{category}" required>
                                </div>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Description</label>
                            <textarea name="description" class="form-control" rows="3" required>{description}</textarea>
                        </div>
                        
                        <div class="form-group">
                            <label>Features (comma separated)</label>
                            <textarea name="features" class="form-control" rows="3" required>{features_str}</textarea>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-4">
                                <div class="form-group">
                                    <label>Original Price ($)</label>
                                    <input type="number" step="0.01" name="original_price" class="form-control" value="{original_price}" required>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="form-group">
                                    <label>Discount Price ($)</label>
                                    <input type="number" step="0.01" name="discount_price" class="form-control" value="{discount_price}">
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="form-group">
                                    <div class="form-check mt-4">
                                        <input type="checkbox" name="has_discount" class="form-check-input" id="hasDiscount" {"checked" if has_discount else ""}>
                                        <label class="form-check-label" for="hasDiscount">Has Discount</label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Tag (optional)</label>
                                    <input type="text" name="tag" class="form-control" value="{tag or ''}" placeholder="e.g., Popular, Recommended, Best Value">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="form-group">
                                    <label>Preview URL</label>
                                    <input type="url" name="preview_url" class="form-control" value="{preview_url or ''}" placeholder="https://demo.example.com">
                                </div>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label>Template Image</label>
                            {"<p class='text-success'><i class='fas fa-check-circle me-2'></i>Current image: " + image_url + "</p>" if image_url else "<p class='text-muted'><i class='fas fa-times-circle me-2'></i>No image uploaded</p>"}
                            <input type="file" name="image" class="form-control" accept="image/*">
                            <small class="text-muted">Leave empty to keep current image</small>
                        </div>
                        
                        <div class="form-group">
                            <div class="form-check">
                                <input type="checkbox" name="status" class="form-check-input" id="status" {"checked" if status == 1 else ""}>
                                <label class="form-check-label" for="status">Active Template</label>
                            </div>
                        </div>
                        
                        <button type="submit" class="btn btn-primary btn-lg w-100 animate-glow">
                            <i class="fas fa-save me-2"></i>Update Template
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/delete-template/<int:template_id>")
@login_required
def admin_delete_template(template_id):
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    template = get_template_by_id(template_id)
    if not template:
        return "Template not found", 404
    
    # Delete image file if exists
    image_url = template[9]
    if image_url and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], image_url)):
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image_url))
        except:
            pass
    
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM templates WHERE id=?", (template_id,))
    con.commit()
    con.close()
    
    return redirect("/admin/templates")

# ---------------- ADMIN ----------------
@app.route("/admin")
@login_required
def admin():
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    
    # Get stats
    stats = {
        "users": 0,
        "orders": 0,
        "pending_orders": 0,
        "custom_orders": 0,
        "templates": 0,
        "submitted_folders": 0
    }
    
    stats["users"] = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    stats["orders"] = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    stats["pending_orders"] = cur.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0]
    stats["custom_orders"] = cur.execute("SELECT COUNT(*) FROM orders WHERE order_type='custom'").fetchone()[0]
    stats["templates"] = cur.execute("SELECT COUNT(*) FROM templates WHERE status=1").fetchone()[0]
    stats["submitted_folders"] = cur.execute("SELECT COUNT(*) FROM orders WHERE folder_submitted=1").fetchone()[0]
    
    # Get recent template orders
    cur.execute("""
        SELECT o.order_id, u.fullname, o.created, o.website_name, o.requirements 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        WHERE o.order_type='template' 
        ORDER BY o.id DESC 
        LIMIT 10
    """)
    recent_template_orders = cur.fetchall()
    
    con.close()
    
    recent_orders_html = ""
    for order in recent_template_orders:
        order_id, fullname, created, website_name, requirements = order
        recent_orders_html += f"""
        <tr class="animate-slide-up">
            <td>{order_id}</td>
            <td>{fullname}</td>
            <td>{website_name or 'N/A'}</td>
            <td>{created}</td>
            <td>
                <a href='/admin/view-order-by-id/{order_id}' class='btn btn-sm btn-outline-primary'>
                    <i class='fas fa-eye'></i>
                </a>
            </td>
        </tr>
        """
    
    return render_base_template("Admin Panel", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <h2 class="mb-3 animate-slide-up">Admin Dashboard</h2>
            
            <div class="row mb-3">
                <div class="col-6 col-md-3 mb-3">
                    <div class="stats-card bg-primary text-white animate-scale-in" style="animation-delay: 0.1s">
                        <div class="card-body text-center">
                            <h5 class="card-title">Users</h5>
                            <h1 class="display-6">{stats['users']}</h1>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3 mb-3">
                    <div class="stats-card bg-success text-white animate-scale-in" style="animation-delay: 0.2s">
                        <div class="card-body text-center">
                            <h5 class="card-title">Orders</h5>
                            <h1 class="display-6">{stats['orders']}</h1>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3 mb-3">
                    <div class="stats-card bg-warning text-white animate-scale-in" style="animation-delay: 0.3s">
                        <div class="card-body text-center">
                            <h5 class="card-title">Pending</h5>
                            <h1 class="display-6">{stats['pending_orders']}</h1>
                        </div>
                    </div>
                </div>
                <div class="col-6 col-md-3 mb-3">
                    <div class="stats-card bg-info text-white animate-scale-in" style="animation-delay: 0.4s">
                        <div class="card-body text-center">
                            <h5 class="card-title">Templates</h5>
                            <h1 class="display-6">{stats['templates']}</h1>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-md-8 mb-3">
                    <div class="card animate-scale-in" style="animation-delay: 0.5s">
                        <div class="card-body">
                            <h5>Recent Template Orders</h5>
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>Order ID</th>
                                            <th>Customer</th>
                                            <th>Website Name</th>
                                            <th>Created</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {recent_orders_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-4">
                    <div class="card animate-scale-in" style="animation-delay: 0.6s">
                        <div class="card-body">
                            <h5>Quick Actions</h5>
                            <hr>
                            <div class="d-grid gap-2">
                                <a href="/admin/orders" class="btn btn-primary">
                                    <i class="fas fa-shopping-cart me-2"></i>All Orders
                                </a>
                                <a href="/admin/users" class="btn btn-secondary">
                                    <i class="fas fa-users me-2"></i>All Users
                                </a>
                                <a href="/admin/templates" class="btn btn-success">
                                    <i class="fas fa-th-large me-2"></i>Manage Templates
                                </a>
                                <a href="/admin/submit-folder" class="btn btn-warning">
                                    <i class="fas fa-upload me-2"></i>Submit Folder
                                </a>
                                <a href="/dashboard" class="btn btn-outline-primary">
                                    <i class="fas fa-home me-2"></i>Dashboard
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/view-order-by-id/<order_id>")
@login_required
def admin_view_order_by_id(order_id):
    if current_user.role != "admin": 
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.*, u.fullname, u.email, u.whatsapp 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        WHERE o.order_id=?
    """, (order_id,))
    order = cur.fetchone()
    
    if not order:
        con.close()
        return "Order not found", 404
    
    # Get messages
    cur.execute("SELECT * FROM messages WHERE order_id=? ORDER BY created", (order[0],))
    messages = cur.fetchall()
    
    con.close()
    
    order_details = {
        "id": order[0],
        "order_id": order[1],
        "user_id": order[2],
        "website_type": order[3],
        "answers": order[4],
        "budget": order[5],
        "stage": order[6],
        "status": order[7],
        "created": order[8],
        "order_type": order[9] if len(order) > 9 else "template",
        "website_name": order[10] if len(order) > 10 else "",
        "requirements": order[11] if len(order) > 11 else "",
        "fullname": order[12],
        "email": order[13],
        "whatsapp": order[14],
        "folder_submitted": order[15] if len(order) > 15 else 0,
        "folder_submitted_at": order[16] if len(order) > 16 else ""
    }
    
    # Parse answers if it's a custom order
    answers_html = ""
    if order_details["order_type"] == "custom" and order_details["answers"]:
        try:
            answers_data = json.loads(order_details["answers"])
            if "answers" in answers_data and "questions" in answers_data:
                questions = answers_data.get("questions", [])
                answers = answers_data.get("answers", [])
                for i in range(min(len(questions), len(answers))):
                    if answers[i]:
                        answers_html += f"""
                        <div class="mb-3">
                            <label class="form-label fw-bold">{questions[i]}</label>
                            <div class="form-control">{answers[i]}</div>
                        </div>
                        """
        except:
            answers_html = f'<div class="alert alert-info">{str(order_details["answers"])[:200]}...</div>'
    
    messages_html = ""
    for msg in messages:
        msg_class = "user-message" if msg[4] == "user" else "bot-message"
        sender_name = order_details["fullname"] if msg[4] == "user" else "You (Admin)"
        messages_html += f"""
        <div class="chat-message {msg_class}">
            <small class="text-muted">{sender_name} • {msg[5]}</small>
            <p class="mb-0">{msg[3]}</p>
        </div>
        """
    
    # Show website name and requirements for template orders
    template_info = ""
    if order_details["order_type"] == "template":
        template_info = f"""
        <div class="mb-3">
            <label class="form-label fw-bold">Website Name</label>
            <div class="form-control">{order_details['website_name'] or 'Not specified'}</div>
        </div>
        <div class="mb-3">
            <label class="form-label fw-bold">Additional Requirements</label>
            <div class="form-control">{order_details['requirements'] or 'No additional requirements'}</div>
        </div>
        """
    
    # Folder submission status
    folder_status = ""
    if order_details.get("folder_submitted") == 1:
        folder_status = f"""
        <div class="alert alert-success">
            <i class="fas fa-check-circle me-2"></i>
            Website folder submitted on {order_details.get('folder_submitted_at', 'N/A')}
            <a href="/admin/submit-folder?order={order_details['order_id']}" class="btn btn-sm btn-outline-success float-end">
                <i class="fas fa-redo me-1"></i>Re-submit
            </a>
        </div>
        """
    else:
        folder_status = f"""
        <div class="alert alert-warning">
            <i class="fas fa-clock me-2"></i>
            Website folder not submitted yet
            <a href="/admin/submit-folder?order={order_details['order_id']}" class="btn btn-sm btn-success float-end">
                <i class="fas fa-upload me-1"></i>Submit Now
            </a>
        </div>
        """
    
    return render_base_template(f"Order {order_details['order_id']}", f'''
    <div class="chat-wrapper animate-scale-in">
        <div class="chat-header">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h4 class="mb-0">Order: {order_details['order_id']}</h4>
                    <p class="text-muted mb-0">{order_details['fullname']} - {order_details['email']}</p>
                </div>
                <div>
                    <a href="/admin/orders" class="btn btn-outline-primary btn-sm me-2">
                        <i class="fas fa-arrow-left me-1"></i>Back
                    </a>
                    <a href="/admin/update/{order_details['id']}" class="btn btn-primary btn-sm">
                        <i class="fas fa-edit me-1"></i>Update
                    </a>
                </div>
            </div>
        </div>
        
        <div class="chat-messages" style="padding: 15px; padding-bottom: 120px;">
            <div class="row">
                <div class="col-md-4">
                    <div class="card mb-3 animate-scale-in" style="animation-delay: 0.1s">
                        <div class="card-body">
                            <h5>Order Information</h5>
                            <hr>
                            <p><strong>Order ID:</strong> {order_details['order_id']}</p>
                            <p><strong>Type:</strong> {order_details['website_type']}</p>
                            <p><strong>Order Type:</strong> {order_details['order_type']}</p>
                            <p><strong>Budget:</strong> ${order_details['budget']}</p>
                            <p><strong>Stage:</strong> {order_details['stage']}</p>
                            <p><strong>Status:</strong> {order_details['status']}</p>
                            <p><strong>Created:</strong> {order_details['created']}</p>
                            
                            <div class="mt-3">
                                <h6>Customer Contact</h6>
                                <p><strong>Name:</strong> {order_details['fullname']}</p>
                                <p><strong>Email:</strong> {order_details['email']}</p>
                                <p><strong>WhatsApp:</strong> {order_details['whatsapp']}</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-8">
                    {folder_status}
                    
                    <div class="card mb-3 animate-scale-in" style="animation-delay: 0.2s">
                        <div class="card-body">
                            {template_info if template_info else ''}
                            {answers_html if answers_html else ''}
                        </div>
                    </div>
                    
                    <div class="card animate-scale-in" style="animation-delay: 0.3s">
                        <div class="card-body">
                            <h5>Communication</h5>
                            <hr>
                            <div style="height: 300px; overflow-y: auto; padding: 10px; background: #f8f9fa; border-radius: 10px;">
                                {messages_html if messages_html else '<div class="text-center text-muted"><i class="fas fa-comments fa-3x mb-3"></i><p>No messages yet</p></div>'}
                            </div>
                            
                            <div class="mt-3">
                                <form method="post" action="/admin/send-message/{order_details['id']}">
                                    <div class="input-group">
                                        <input type="text" name="message" class="form-control chat-input" placeholder="Type your message as admin..." required>
                                        <button class="chat-send-btn" type="submit">
                                            <i class="fas fa-paper-plane"></i> Send
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    ''')

@app.route("/admin/orders")
@login_required
def admin_orders():
    if current_user.role != "admin": 
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    
    cur.execute("""
        SELECT o.id, o.order_id, o.website_type, o.stage, o.status, o.created, 
               u.fullname, u.email, o.order_type, o.website_name, o.requirements, o.folder_submitted 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        ORDER BY o.id DESC
    """)
    
    rows = cur.fetchall()
    con.close()
    
    orders_html = ""
    for order in rows:
        order_id, order_number, website_type, stage, status, created, fullname, email, order_type, website_name, requirements, folder_submitted = order
        status_color = "success" if status == "Granted" else "warning" if status == "Pending" else "info"
        order_type_badge = "primary" if order_type == "custom" else "secondary" if order_type == "template" else "info"
        folder_badge = "success" if folder_submitted == 1 else "secondary"
        folder_text = "Submitted" if folder_submitted == 1 else "Pending"
        
        orders_html += f"""
        <tr class="animate-slide-up">
            <td>
                <strong>{order_number}</strong><br>
                <small class="text-muted">{fullname}</small>
            </td>
            <td>{website_type}</td>
            <td>{stage}</td>
            <td><span class="badge bg-{status_color}">{status}</span></td>
            <td>{created}</td>
            <td><span class="badge bg-{order_type_badge}">{order_type.upper() if order_type else 'TEMPLATE'}</span></td>
            <td>{website_name or 'N/A'}</td>
            <td><span class="badge bg-{folder_badge}">{folder_text}</span></td>
            <td>
                <a href='/admin/view-order-by-id/{order_number}' class='btn btn-sm btn-outline-primary'>
                    <i class='fas fa-eye'></i>
                </a>
            </td>
        </tr>
        """
    
    return render_base_template("Admin Orders", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">All Orders</h2>
                <a href="/admin" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            
            <div class="card animate-scale-in" style="animation-delay: 0.2s">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Order/Customer</th>
                                    <th>Type</th>
                                    <th>Stage</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Order Type</th>
                                    <th>Website Name</th>
                                    <th>Folder</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {orders_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/send-message/<int:order_id>", methods=["POST"])
@login_required
def admin_send_message(order_id):
    if current_user.role != "admin":
        return redirect("/dashboard")
    
    message = request.form.get("message", "").strip()
    if not message:
        return redirect(f"/admin/view-order-by-id/{order_id}")
    
    con = db()
    cur = con.cursor()
    
    # Get user_id and order_number from order
    cur.execute("SELECT user_id, order_id FROM orders WHERE id=?", (order_id,))
    order_data = cur.fetchone()
    
    if order_data:
        user_id = order_data[0]
        order_number = order_data[1]
        
        # Add message
        cur.execute("""INSERT INTO messages (order_id, user_id, message, sender) 
                      VALUES(?,?,?,?)""", 
                    (order_id, user_id, message, "admin"))
        
        # Add notification
        cur.execute("""INSERT INTO notifications (user_id, message, sender_id) 
                      VALUES(?,?,?)""", 
                    (user_id, f"New message from admin regarding order {order_number}: {message}", current_user.id))
        
        con.commit()
    
    con.close()
    return redirect(f"/admin/view-order-by-id/{order_number}")

@app.route("/admin/update/<int:id>", methods=["GET","POST"])
@login_required
def update(id):
    if current_user.role != "admin": 
        return redirect("/dashboard")
    
    if request.method == "POST":
        stage = request.form["stage"]
        status = request.form["status"]
        
        con = db()
        cur = con.cursor()
        
        # Get user_id and order_id from order
        cur.execute("SELECT user_id, order_id FROM orders WHERE id=?", (id,))
        order_data = cur.fetchone()
        
        if order_data:
            user_id = order_data[0]
            order_id = order_data[1]
            
            # Update order
            cur.execute("UPDATE orders SET stage=?, status=? WHERE id=?", (stage, status, id))
            
            # Add notification
            notification_msg = f"Your order {order_id} status has been updated: Stage - {stage}, Status - {status}"
            cur.execute("INSERT INTO notifications(user_id,message,sender_id) VALUES(?,?,?)",
                        (user_id, notification_msg, current_user.id))
            
            con.commit()
        
        con.close()
        return redirect("/admin/orders")

    return render_base_template("Update Order", """
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <div class="card animate-scale-in">
                        <div class="card-body">
                            <h3 class="text-center mb-3">Update Order Status</h3>
                            <form method="post">
                                <div class="mb-3">
                                    <label class="form-label">Stage</label>
                                    <input name="stage" class="form-control" placeholder="e.g., Development, Testing, Completed" required>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Status</label>
                                    <select name="status" class="form-control" required>
                                        <option value="Pending">Pending</option>
                                        <option value="In Progress">In Progress</option>
                                        <option value="Completed">Completed</option>
                                        <option value="Granted">Granted</option>
                                        <option value="Cancelled">Cancelled</option>
                                    </select>
                                </div>
                                
                                <button class="btn btn-success w-100 btn-lg animate-glow">
                                    <i class="fas fa-save me-2"></i>Update Status
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.role != "admin": 
        return redirect("/dashboard")
    
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, fullname, email, whatsapp, role, created FROM users ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    
    users_html = ""
    for user in rows:
        user_id, fullname, email, whatsapp, role, created = user
        role_badge = "danger" if role == "admin" else "primary"
        
        users_html += f"""
        <tr class="animate-slide-up">
            <td>{user_id}</td>
            <td>{fullname}</td>
            <td>{email}</td>
            <td>{whatsapp}</td>
            <td><span class="badge bg-{role_badge}">{role}</span></td>
            <td>{created if created else 'N/A'}</td>
        </tr>
        """
    
    return render_base_template("Manage Users", f"""
    <div class="content-wrapper">
        <div style="padding: 15px;">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h2 class="mb-0 animate-slide-up">Manage Users</h2>
                <a href="/admin" class="btn btn-outline-primary btn-sm animate-slide-up" style="animation-delay: 0.1s">
                    <i class="fas fa-arrow-left me-2"></i>Back
                </a>
            </div>
            
            <div class="card animate-scale-in" style="animation-delay: 0.2s">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Full Name</th>
                                    <th>Email</th>
                                    <th>WhatsApp</th>
                                    <th>Role</th>
                                    <th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """)

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

if __name__ == "__main__":
    # Create placeholder image files if they don't exist
    default_images = [
        "ecommerce.png", "business.png", "blog.png", "portfolio.png",
        "education.png", "social.png", "news.png", "event.png", "forum.png"
    ]
    
    for image_name in default_images:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        if not os.path.exists(image_path):
            # Create empty file as placeholder
            with open(image_path, 'wb') as f:
                pass
    
    
    app.run(host="0.0.0.0", port=5000, debug=True)
