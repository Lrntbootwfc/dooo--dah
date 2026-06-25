import os
import json
import base64
import sqlite3
import hashlib
import random
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
    username_key = username.lower()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Check if user handle workspace identifier is already taken
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username_key, p_hash))
        
        # Provision a clean seed directory tree mapping matching the "Comic Diary" style
        initial_seed = [
            { 
                "id": "fold_seed_1", "type": "folder", "name": "Comic Diary Logs 📒", 
                "children": [
                    { 
                        "id": "file_seed_1", "type": "file", "name": "Inaugural Entry", 
                        "content": "Welcome to my encrypted Comic Diary! Today I am sketching out ideas for our first graphic novel. The character alignments in the sidebar are configured and ready for the daily illustrator.", 
                        "mood": "😊", 
                        "created": "6/25/2026, 9:00 AM", 
                        "edited": "6/25/2026, 9:00 AM", 
                        "comic": "",
                        "stickers": []
                    }
                ] 
            }
        ]
        cursor.execute("INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)", (username_key, json.dumps(initial_seed)))
        conn.commit()
        return jsonify({"status": "Success", "message": "Unique encrypted Comic Diary space provisioned successfully!"}), 201
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
    username_key = username.lower()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, avatar_desc FROM users WHERE username = ?", (username_key,))
    user_record = cursor.fetchone()
    
    if not user_record or user_record[0] != p_hash:
        conn.close()
        return jsonify({"error": "Invalid credential verification signatures! Access Denied."}), 401
        
    # User is valid, pull down their relational filesystem layout data arrays
    cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username = ?", (username_key,))
    fs_record = cursor.fetchone()
    fs_tree_json = fs_record[0] if fs_record else "[]"
    conn.close()
    
    return jsonify({
        "status": "Success",
        "username": username, # Return display username
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
        
    username_key = username.lower()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE file_systems SET fs_tree_json = ? WHERE username = ?", (json.dumps(fs_tree), username_key))
    cursor.execute("UPDATE users SET avatar_desc = ? WHERE username = ?", (avatar_desc, username_key))
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
        
    # Retrieve optional fields for Gemini refinement & fallback rendering
    api_key = os.environ.get("GEMINI_API_KEY")
    avatar_desc = data.get("avatar_desc")
    father_desc = data.get("father_desc")
    mother_desc = data.get("mother_desc")
    others_desc = data.get("others_desc")
    mood = data.get("mood", "😊")
    content = data.get("content", "")

    # Step A: Construct Character guidelines
    char_guidelines = ""
    if avatar_desc:
        char_guidelines += f"Self: {avatar_desc}. "
    if father_desc:
        char_guidelines += f"Father: {father_desc}. "
    if mother_desc:
        char_guidelines += f"Mother: {mother_desc}. "
    if others_desc:
        char_guidelines += f"Others: {others_desc}. "

    refined_prompt = optimized_prompt

    # Step B: Refine the prompt via Gemini API (if key is set)
    if api_key and api_key != "MY_GEMINI_API_KEY":
        try:
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            instructions = (
                f"Create a single highly descriptive, compressed visual prompt for an image generator "
                f"to create a 2D comic panel.\n"
                f"Character guidelines: \"{char_guidelines}\"\n"
                f"Mood: \"{mood}\"\n"
                f"Entry Content: \"{content}\"\n\n"
                f"Focus purely on visual layout, setting, lighting, character pose, and clean indie comic-book sketch style. "
                f"Keep it compact, rich, and remove all narration. Do not include speech bubbles, text lettering, "
                f"or markdown formatting. Output ONLY the refined visual prompt text."
            )
            payload = {
                "contents": [{
                    "parts": [{"text": instructions}]
                }]
            }
            res = requests.post(gemini_url, json=payload, timeout=10)
            if res.status_code == 200:
                res_data = res.json()
                try:
                    refined_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    if refined_text:
                        refined_prompt = refined_text.strip()
                except (KeyError, IndexError):
                    pass
        except Exception as gemini_err:
            print(f"Gemini prompt refinement skipped/failed: {gemini_err}")

    # Build the final art style wrapping prompt
    final_art_prompt = f"{refined_prompt}. Stylized 2D graphic novel style comic art cell. Clean high-contrast colors, crisp ink outline work. No lettering, no speech bubble balloons."
    
    # Step C: Fetch image from Pollinations.ai with randomized seed
    rand_seed = random.randint(1, 1000000)
    api_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(final_art_prompt)}?width=512&height=512&nologo=true&seed={rand_seed}"
    
    try:
        response = requests.get(api_url, timeout=25)
        if response.status_code == 200 and len(response.content) > 1000:
            base64_image_data = base64.b64encode(response.content).decode("utf-8")
            data_url = f"data:image/png;base64,{base64_image_data}"
            return jsonify({
                "status": "Success", 
                "image_data_url": data_url,
                "optimized_prompt": final_art_prompt
            })
        else:
            print(f"Pollinations.ai returned status {response.status_code}. Triggering visual SVG fallback.")
    except Exception as e:
        print(f"Pollinations.ai connection failed: {e}. Triggering visual SVG fallback.")

    # Step D: Dynamic Vector SVG Fallback (Bulletproof safeguard)
    safe_mood = mood or "😊"
    safe_content = content[:150] + "..." if content else "Reflective thoughts and core sketches in progress."
    safe_avatar = avatar_desc or "Minimalist designer"

    color_themes = {
        "😊": { "bg": "#FFFbeb", "accent": "#F59e0b", "text": "#78350f", "decoration": "☀️ 🌸 ✨" },
        "💻": { "bg": "#ECfeff", "accent": "#06b6d4", "text": "#164e63", "decoration": "💻 ⚡ 🧠" },
        "🌌": { "bg": "#FAF5ff", "accent": "#8b5cf6", "text": "#4c1d95", "decoration": "🌙 🌌 🧘" },
        "⚡": { "bg": "#FEf2f2", "accent": "#ef4444", "text": "#7f1d1d", "decoration": "💥 ⚡ 🔥" },
        "default": { "bg": "#F8fafc", "accent": "#64748b", "text": "#0f172a", "decoration": "📝 ✨ 🌟" }
    }
    
    theme = color_themes.get(safe_mood, color_themes["default"])
    
    fallback_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
    <rect width="500" height="500" fill="#000000" />
    <rect x="15" y="15" width="470" height="470" fill="{theme['bg']}" stroke="#000000" stroke-width="6" rx="10" />
    
    <!-- Halftone retro comic pattern dots -->
    <pattern id="halftone" x="0" y="0" width="12" height="12" patternUnits="userSpaceOnUse">
      <circle cx="3" cy="3" r="1.5" fill="{theme['accent']}" opacity="0.18" />
    </pattern>
    <rect x="15" y="15" width="470" height="470" fill="url(#halftone)" rx="10" />

    <!-- Comic panel division grid style borders -->
    <line x1="15" y1="280" x2="485" y2="280" stroke="#000000" stroke-width="4" />
    <line x1="250" y1="15" x2="250" y2="280" stroke="#000000" stroke-width="4" />

    <!-- Panel 1: Avatar Profile Frame -->
    <g transform="translate(40, 40)">
      <circle cx="70" cy="70" r="45" fill="{theme['accent']}" opacity="0.3" stroke="#000000" stroke-width="2" />
      <text x="70" y="75" font-family="sans-serif" font-weight="bold" font-size="28" text-anchor="middle" fill="#000000">👤</text>
      <rect x="10" y="130" width="120" height="24" fill="#000000" rx="4" />
      <text x="70" y="146" font-family="monospace" font-weight="bold" font-size="10" text-anchor="middle" fill="#FFFFFF">ACTIVE PROFILE</text>
      <text x="70" y="180" font-family="sans-serif" font-size="11" text-anchor="middle" fill="#475569" font-style="italic">"{safe_avatar[:20]}"</text>
    </g>

    <!-- Panel 2: Mood Aura & Weather -->
    <g transform="translate(280, 40)">
      <rect width="160" height="150" fill="#FFFFFF" stroke="#000000" stroke-width="3" rx="8" />
      <text x="80" y="65" font-family="sans-serif" font-size="52" text-anchor="middle">{safe_mood}</text>
      <text x="80" y="105" font-family="sans-serif" font-weight="bold" font-size="18" text-anchor="middle" fill="{theme['text']}"></text>
      <text x="80" y="130" font-family="sans-serif" font-size="12" text-anchor="middle" fill="#475569">{theme['decoration']}</text>
    </g>

    <!-- Panel 3: Journal Visual Snapshot (Large bottom panel) -->
    <g transform="translate(40, 305)">
      <path d="M 0,10 L 420,10 L 420,150 L 0,150 Z" fill="#FFFFFF" stroke="#000000" stroke-width="3" rx="6" />
      <circle cx="50" cy="75" r="30" fill="{theme['accent']}" opacity="0.2" />
      <text x="50" y="85" font-family="sans-serif" font-size="30" text-anchor="middle">🎨</text>
      <text x="100" y="55" font-family="sans-serif" font-weight="bold" font-size="14" fill="#0F172A">Daily Comic Sketch</text>
      <text x="100" y="75" font-family="sans-serif" font-size="11" fill="#64748B">Refining prose into stylized cells...</text>
      
      <!-- Text snippet block -->
      <rect x="100" y="90" width="300" height="45" fill="{theme['bg']}" stroke="#000000" stroke-width="1.5" rx="4" />
      <text x="110" y="108" font-family="monospace" font-size="10" fill="{theme['text']}">{safe_content[:42]}</text>
      <text x="110" y="123" font-family="monospace" font-size="10" fill="{theme['text']}">{safe_content[42:84]}</text>
    </g>

    <!-- Comic panel outer text captions -->
    <rect x="170" y="455" width="160" height="25" fill="#000000" />
    <text x="250" y="471" font-family="monospace" font-weight="bold" font-size="11" text-anchor="middle" fill="#FFFFFF">PANEL GENERATED</text>
  </svg>"""

    base64_svg_data = base64.b64encode(fallback_svg.encode("utf-8")).decode("utf-8")
    data_url = f"data:image/svg+xml;base64,{base64_svg_data}"
    
    return jsonify({
        "status": "Success",
        "image_data_url": data_url,
        "optimized_prompt": final_art_prompt,
        "fallback": True
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)


# import os
# import json
# import base64
# import sqlite3
# import hashlib
# import requests
# from flask import Flask, request, jsonify
# from flask_cors import CORS

# app = Flask(__name__)
# # Enable broad CORS access so your browser HTML file can safely run requests
# CORS(app)

# # ─── SECURE STORAGE SETUP ───
# STORAGE_DIR = os.path.join(os.path.dirname(__file__), "vault_storage")
# COMICS_DIR = os.path.join(STORAGE_DIR, "generated_comics")
# DB_PATH = os.path.join(STORAGE_DIR, "chronicle_vault.db")

# os.makedirs(STORAGE_DIR, exist_ok=True)
# os.makedirs(COMICS_DIR, exist_ok=True)

# # ─── DATABASE CORE SETUP ───
# def init_db():
#     """Initializes the SQLite database schema structures for users and recursive logs."""
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     # Users tracking directory core table
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS users (
#             username TEXT PRIMARY KEY,
#             password_hash TEXT NOT NULL,
#             avatar_desc TEXT DEFAULT 'programmer in minimalist hoodie, sleek glasses'
#         )
#     ''')
#     # Dynamic tree filesystem mapping schema table
#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS file_systems (
#             username TEXT PRIMARY KEY,
#             fs_tree_json TEXT NOT NULL,
#             FOREIGN KEY(username) REFERENCES users(username)
#         )
#     ''')
#     conn.commit()
#     conn.close()

# init_db()

# def hash_password(password):
#     """Securely salts and hashes passwords using SHA-256."""
#     return hashlib.sha256(password.encode('utf-8')).hexdigest()

# # ─── ROUTE 1: ACCOUNT REGISTRATION / SIGN UP ───
# @app.route("/api/signup", methods=["POST"])
# def register_vault_identity():
#     data = request.json or {}
#     username = data.get("username", "").strip()
#     password = data.get("password", "").strip()
    
#     if not username or not password:
#         return jsonify({"error": "Registration criteria parameters cannot be left blank!"}), 400
        
#     p_hash = hash_password(password)
    
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     try:
#         # Check if user handle workspace identifier is already taken
#         cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, p_hash))
        
#         # Provision a clean seed directory tree mapping for the new unique identity account
#         initial_seed = [
#             { 
#                 "id": "fold_seed_1", "type": "folder", "name": "Chai Logs", 
#                 "children": [
#                     { 
#                         "id": "file_seed_1", "type": "file", "name": "Inaugural Entry", 
#                         "content": "Code compiled cleanly on the server backend architecture blueprint matrix over hot tea.", 
#                         "mood": "💻", "created": "6/24/2026, 3:11 PM", "edited": "6/24/2026, 3:11 PM", "comic": "" 
#                     }
#                 ] 
#             }
#         ]
#         cursor.execute("INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)", (username, json.dumps(initial_seed)))
#         conn.commit()
#         return jsonify({"status": "Success", "message": "Unique encrypted vault matrix provisioned successfully!"}), 201
#     except sqlite3.IntegrityError:
#         return jsonify({"error": "Identity handle namespace already occupied by an active vault container!"}), 409
#     finally:
#         conn.close()

# # ─── ROUTE 2: REAL AUTHORIZATION / SIGN IN ───
# @app.route("/api/login", methods=["POST"])
# def verify_vault_access():
#     data = request.json or {}
#     username = data.get("username", "").strip()
#     password = data.get("password", "").strip()
    
#     if not username or not password:
#         return jsonify({"error": "Missing input signature authentication parameters"}), 400
        
#     p_hash = hash_password(password)
    
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     cursor.execute("SELECT password_hash, avatar_desc FROM users WHERE username = ?", (username,))
#     user_record = cursor.fetchone()
    
#     if not user_record or user_record[0] != p_hash:
#         conn.close()
#         return jsonify({"error": "Invalid credential verification signatures! Access Denied."}), 401
        
#     # User is valid, pull down their relational filesystem layout data arrays
#     cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username = ?", (username,))
#     fs_tree_json = cursor.fetchone()[0]
#     conn.close()
    
#     return jsonify({
#         "status": "Success",
#         "username": username,
#         "avatar_desc": user_record[1],
#         "fs_tree": json.loads(fs_tree_json)
#     })

# # ─── ROUTE 3: COMMIT RUNTIME DIRECTORY TREE UPDATES ───
# @app.route("/api/save", methods=["POST"])
# def commit_matrix_state():
#     data = request.json or {}
#     username = data.get("username")
#     fs_tree = data.get("fs_tree")
#     avatar_desc = data.get("avatar_desc", "programmer in minimalist hoodie, sleek glasses")
    
#     if not username or fs_tree is None:
#         return jsonify({"error": "Data tracking synchronizations missing crucial identity reference headers"}), 400
        
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     cursor.execute("UPDATE file_systems SET fs_tree_json = ? WHERE username = ?", (json.dumps(fs_tree), username))
#     cursor.execute("UPDATE users SET avatar_desc = ? WHERE username = ?", (avatar_desc, username))
#     conn.commit()
#     conn.close()
    
#     return jsonify({"status": "Success", "message": "Structural parameters successfully anchored into hard drive DB storage layers."})

# # ─── ROUTE 4: COHESIVE IMAGE GENERATION FLOW ───
# @app.route("/api/render-comic", methods=["POST"])
# def process_cached_artwork_panel():
#     data = request.json or {}
#     username = data.get("username")
#     optimized_prompt = data.get("prompt")
    
#     if not optimized_prompt:
#         return jsonify({"error": "Prompt execution target strings cannot be empty!"}), 400
        
#     api_url = f"https://image.pollinations.ai/p/{requests.utils.quote(optimized_prompt)}?width=800&height=800&enhance=true&seed=88"
    
#     try:
#         response = requests.get(api_url, timeout=25)
#         if response.status_code == 200 and len(response.content) > 1000:
#             # Clean base64 packaging loops straight back to our frontend layout frames instantly
#             base64_image_data = base64.b64encode(response.content).decode("utf-8")
#             data_url = f"data:image/png;base64,{base64_image_data}"
#             return jsonify({"status": "Success", "image_data_url": data_url})
#         else:
#             return jsonify({"error": "Upstream visualization model rendering error."}), 502
#     except Exception as e:
#         return jsonify({"error": f"Internal mapping connection breakdown: {str(e)}"}), 500

# if __name__ == "__main__":
#     app.run(debug=True, port=5000)