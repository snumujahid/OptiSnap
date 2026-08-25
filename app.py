import streamlit as st
import sqlite3
import hashlib
import datetime
import os

st.set_page_config(page_title="Class SnapBoard", page_icon="📸", layout="centered")

# --- DATABASE SETUP ---
DB_FILE = "snapboard.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Snaps Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS snaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            caption TEXT,
            image_path TEXT,
            created_at TIMESTAMP,
            expires_at TIMESTAMP
        )
    ''')
    
    # Default instructor/admin account: username='instructor', password='admin123'
    admin_hash = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute('''
        INSERT OR IGNORE INTO users (username, password_hash, is_admin)
        VALUES ('instructor', ?, 1)
    ''', (admin_hash,))
    
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_details(username):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username.lower(),))
    user = c.fetchone()
    conn.close()
    return user

def create_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                  (username.lower(), hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_snap(snap_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT image_path FROM snaps WHERE id = ?", (snap_id,))
    snap = c.fetchone()
    if snap and snap['image_path'] and os.path.exists(snap['image_path']):
        try:
            os.remove(snap['image_path'])
        except OSError:
            pass
    c.execute("DELETE FROM snaps WHERE id = ?", (snap_id,))
    conn.commit()
    conn.close()

def toggle_user_ban(username, ban_status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = ? WHERE username = ?", (1 if ban_status else 0, username))
    conn.commit()
    conn.close()

if not os.path.exists("uploads"):
    os.makedirs("uploads")

# --- SESSION STATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- AUTHENTICATION UI ---
if not st.session_state.authenticated:
    st.title("📸 Class SnapBoard")
    st.subheader("Login or Register to Join")

    tab1, tab2 = st.tabs(["🔒 Login", "📝 Register"])

    with tab1:
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In")
            if submit:
                user = get_user_details(username_input)
                if user and user['password_hash'] == hash_password(password_input):
                    if user['is_banned']:
                        st.error("🚫 This account has been banned by the instructor.")
                    else:
                        st.session_state.authenticated = True
                        st.session_state.username = user['username']
                        st.session_state.is_admin = bool(user['is_admin'])
                        st.rerun()
                else:
                    st.error("Invalid username or password.")

    with tab2:
        with st.form("register_form"):
            new_username = st.text_input("Choose Username")
            new_password = st.text_input("Choose Password", type="password")
            reg_submit = st.form_submit_button("Create Account")
            if reg_submit:
                if len(new_username) < 3 or len(new_password) < 4:
                    st.warning("Username must be >= 3 chars and password >= 4 chars.")
                else:
                    if create_user(new_username, new_password):
                        st.success("Account created! Please log in.")
                    else:
                        st.error("Username already exists.")

    st.stop()

# --- SIDEBAR & USER CONTROLS ---
st.sidebar.title(f"👋 @{st.session_state.username}")
if st.session_state.is_admin:
    st.sidebar.success("🛡️ Instructor Mode")

if st.sidebar.button("Log Out"):
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.is_admin = False
    st.rerun()

# Instructor User Moderation Panel
if st.session_state.is_admin:
    with st.sidebar.expander("🛠️ User Moderation"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT username, is_admin, is_banned FROM users WHERE is_admin = 0")
        students = c.fetchall()
        conn.close()

        if not students:
            st.write("No students registered yet.")
        else:
            for student in students:
                col_u, col_b = st.columns([2, 1])
                with col_u:
                    status = "🚫 Banned" if student['is_banned'] else "✅ Active"
                    st.write(f"**@{student['username']}** ({status})")
                with col_b:
                    if student['is_banned']:
                        if st.button("Unban", key=f"unban_{student['username']}"):
                            toggle_user_ban(student['username'], False)
                            st.rerun()
                    else:
                        if st.button("Ban", key=f"ban_{student['username']}"):
                            toggle_user_ban(student['username'], True)
                            st.rerun()

st.title("🔥 Class SnapBoard")

# --- CREATE SNAP FORM ---
with st.expander("📸 Post a New Snap", expanded=True):
    with st.form("new_snap_form", clear_on_submit=True):
        caption = st.text_area("Question, Caption, or LaTeX Math ($...$):", "")
        uploaded_file = st.file_uploader("Upload Image/Diagram", type=["png", "jpg", "jpeg"])
        ttl_minutes = st.slider("Snap Expiry (minutes):", min_value=1, max_value=1440, value=30)
        
        send_snap = st.form_submit_button("Post Snap 🚀")

        if send_snap and (caption or uploaded_file):
            now = datetime.datetime.now()
            expires_at = now + datetime.timedelta(minutes=ttl_minutes)
            
            image_path = None
            if uploaded_file:
                image_path = os.path.join("uploads", f"{now.timestamp()}_{uploaded_file.name}")
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''
                INSERT INTO snaps (author, caption, image_path, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (st.session_state.username, caption, image_path, now, expires_at))
            conn.commit()
            conn.close()

            st.success("Snap posted!")
            st.rerun()

# --- CLASS FEED ---
st.divider()
st.subheader("🌐 Class Feed")

conn = get_db_connection()
c = conn.cursor()
now_str = datetime.datetime.now()
c.execute("SELECT * FROM snaps WHERE expires_at > ? ORDER BY id DESC", (now_str,))
active_snaps = c.fetchall()
conn.close()

if not active_snaps:
    st.info("No active snaps in the feed right now.")
else:
    for snap in active_snaps:
        expires_dt = datetime.datetime.strptime(snap['expires_at'].split(".")[0], "%Y-%m-%d %H:%M:%S")
        mins_left = max(0, int((expires_dt - datetime.datetime.now()).total_seconds() // 60))

        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**@{snap['author']}**")
            with col2:
                st.caption(f"⏳ {mins_left}m left")
            with col3:
                if st.session_state.is_admin or st.session_state.username == snap['author']:
                    if st.button("🗑️ Delete", key=f"del_{snap['id']}"):
                        delete_snap(snap['id'])
                        st.rerun()

            if snap['image_path'] and os.path.exists(snap['image_path']):
                st.image(snap['image_path'], use_column_width=True)

            if snap['caption']:
                st.write(snap['caption'])

            st.divider()
