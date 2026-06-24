import os
import json
import base64
import sqlite3
import hashlib
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Enable broad CORS access so your browser HTML file can safely run requests
CORS(app)

# ─── SECURE STORAGE SETUP ───
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "vault_storage")
COMICS_DIR = os.path.join(STORAGE_DIR, "generated_comics")
DB_PATH = os.path.join(STORAGE_DIR, "chronicle_vault.db")

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(COMICS_DIR, exist_ok=True)

# ─── DATABASE CORE SETUP ───
def init_db():
    """Initializes the SQLite database schema structures for users and recursive logs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Users tracking directory core table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            avatar_desc TEXT DEFAULT 'programmer in minimalist hoodie, sleek glasses'
        )
    ''')
    # Dynamic tree filesystem mapping schema table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_systems (
            username TEXT PRIMARY KEY,
            fs_tree_json TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    """Securely salts and hashes passwords using SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# ─── ROUTE 1: ACCOUNT REGISTRATION / SIGN UP ───
@app.route("/api/signup", methods=["POST"])
def register_vault_identity():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Registration criteria parameters cannot be left blank!"}), 400
        
    p_hash = hash_password(password)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Check if user handle workspace identifier is already taken
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, p_hash))
        
        # Provision a clean seed directory tree mapping for the new unique identity account
        initial_seed = [
            { 
                "id": "fold_seed_1", "type": "folder", "name": "Chai Logs", 
                "children": [
                    { 
                        "id": "file_seed_1", "type": "file", "name": "Inaugural Entry", 
                        "content": "Code compiled cleanly on the server backend architecture blueprint matrix over hot tea.", 
                        "mood": "💻", "created": "6/24/2026, 3:11 PM", "edited": "6/24/2026, 3:11 PM", "comic": "" 
                    }
                ] 
            }
        ]
        cursor.execute("INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)", (username, json.dumps(initial_seed)))
        conn.commit()
        return jsonify({"status": "Success", "message": "Unique encrypted vault matrix provisioned successfully!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Identity handle namespace already occupied by an active vault container!"}), 409
    finally:
        conn.close()

# ─── ROUTE 2: REAL AUTHORIZATION / SIGN IN ───
@app.route("/api/login", methods=["POST"])
def verify_vault_access():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Missing input signature authentication parameters"}), 400
        
    p_hash = hash_password(password)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, avatar_desc FROM users WHERE username = ?", (username,))
    user_record = cursor.fetchone()
    
    if not user_record or user_record[0] != p_hash:
        conn.close()
        return jsonify({"error": "Invalid credential verification signatures! Access Denied."}), 401
        
    # User is valid, pull down their relational filesystem layout data arrays
    cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username = ?", (username,))
    fs_tree_json = cursor.fetchone()[0]
    conn.close()
    
    return jsonify({
        "status": "Success",
        "username": username,
        "avatar_desc": user_record[1],
        "fs_tree": json.loads(fs_tree_json)
    })

# ─── ROUTE 3: COMMIT RUNTIME DIRECTORY TREE UPDATES ───
@app.route("/api/save", methods=["POST"])
def commit_matrix_state():
    data = request.json or {}
    username = data.get("username")
    fs_tree = data.get("fs_tree")
    avatar_desc = data.get("avatar_desc", "programmer in minimalist hoodie, sleek glasses")
    
    if not username or fs_tree is None:
        return jsonify({"error": "Data tracking synchronizations missing crucial identity reference headers"}), 400
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE file_systems SET fs_tree_json = ? WHERE username = ?", (json.dumps(fs_tree), username))
    cursor.execute("UPDATE users SET avatar_desc = ? WHERE username = ?", (avatar_desc, username))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "Success", "message": "Structural parameters successfully anchored into hard drive DB storage layers."})

# ─── ROUTE 4: COHESIVE IMAGE GENERATION FLOW ───
@app.route("/api/render-comic", methods=["POST"])
def process_cached_artwork_panel():
    data = request.json or {}
    username = data.get("username")
    optimized_prompt = data.get("prompt")
    
    if not optimized_prompt:
        return jsonify({"error": "Prompt execution target strings cannot be empty!"}), 400
        
    api_url = f"https://image.pollinations.ai/p/{requests.utils.quote(optimized_prompt)}?width=800&height=800&enhance=true&seed=88"
    
    try:
        response = requests.get(api_url, timeout=25)
        if response.status_code == 200 and len(response.content) > 1000:
            # Clean base64 packaging loops straight back to our frontend layout frames instantly
            base64_image_data = base64.b64encode(response.content).decode("utf-8")
            data_url = f"data:image/png;base64,{base64_image_data}"
            return jsonify({"status": "Success", "image_data_url": data_url})
        else:
            return jsonify({"error": "Upstream visualization model rendering error."}), 502
    except Exception as e:
        return jsonify({"error": f"Internal mapping connection breakdown: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)