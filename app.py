import os
import json
import base64
import sqlite3
import hashlib
import random
import requests
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# 🔓 Enable CORS for all routes, origins, and credentials
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ─── STORAGE SETUP ───
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "vault_storage")
COMICS_DIR  = os.path.join(STORAGE_DIR, "generated_comics")
DB_PATH     = os.path.join(STORAGE_DIR, "chronicle_vault.db")
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(COMICS_DIR,  exist_ok=True)

# ─── DATABASE INIT ───────────────────────────────────────────────────────────
def init_db():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username          TEXT PRIMARY KEY,
            password_hash     TEXT NOT NULL,
            avatar_desc       TEXT DEFAULT 'programmer in minimalist hoodie, sleek glasses',
            global_alignments TEXT DEFAULT '{}'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_systems (
            username     TEXT PRIMARY KEY,
            fs_tree_json TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otp_verifications (
            target     TEXT PRIMARY KEY,
            otp_code   TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN global_alignments TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass   
    conn.commit()
    conn.close()

init_db()

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def parse_data_url(data_url):
    if not data_url:
        return None
    try:
        if "," in data_url:
            header, encoded = data_url.split(",", 1)
            mime_type = "image/png"
            if "data:" in header:
                mime_type = header.split(";")[0].replace("data:", "")
            return {"mimeType": mime_type, "data": encoded}
    except Exception as e:
        print(f"parse_data_url error: {e}")
    return None

def _get_conn():
    return sqlite3.connect(DB_PATH)

# ─── SAFE SMTP INFRASTRUCTURE ────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", os.environ.get("SMTP_SERVER", "smtp.gmail.com")).strip()
SMTP_USER = os.environ.get("SMTP_USER", os.environ.get("SMTP_USERNAME", "")).strip()
SMTP_PASS = os.environ.get("SMTP_PASS", os.environ.get("SMTP_PASSWORD", "")).strip()

raw_port = str(os.environ.get("SMTP_PORT", "587")).strip()
SMTP_PORT = int(raw_port) if raw_port.isdigit() else 587

otp_store: dict = {}

def _send_email_otp(to_email: str, code: str) -> tuple[bool, str]:
    print(f"[DEBUG] Attempting OTP to {to_email} via {SMTP_HOST}:{SMTP_PORT} using user {SMTP_USER}")
    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "🔐 Comic Diary — Email Verification Code"
            msg["From"]    = f'"Comic Diary Auth" <{SMTP_USER}>'
            msg["To"]      = to_email
            html_content = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #ffffff; border-radius: 12px;">
                <h2 style="color: #ec4899; margin-bottom: 8px;">Verification Code</h2>
                <p style="color: #cbd5e1; font-size: 14px;">Your one-time verification passcode for Comic Diary is:</p>
                <div style="background-color: #1e293b; padding: 16px; border-radius: 8px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #38bdf8; margin: 20px 0;">
                    {code}
                </div>
                <p style="font-size: 12px; color: #94a3b8;">This code expires in 10 minutes. Do not share it with anyone.</p>
            </div>
            """
            msg.attach(MIMEText(html_content, "html"))

            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
                server.starttls()

            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())
            server.quit()
            print(f"[SMTP SUCCESS] Real OTP sent to {to_email}")
            return True, "Email sent successfully"
        except Exception as e:
            err_msg = f"SMTP Error: {str(e)}"
            print(f"[SMTP ERROR] {err_msg}")
            traceback.print_exc()
            return False, err_msg
    return False, "SMTP_USER or SMTP_PASS not configured"

# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/signup", methods=["POST"])
def register_vault_identity():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    p_hash       = hash_password(password)
    username_key = username.lower()
    initial_seed = _build_initial_seed()
    conn   = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username_key, p_hash)
        )
        cursor.execute(
            "INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)",
            (username_key, json.dumps(initial_seed))
        )
        conn.commit()
        return jsonify({"status": "Success", "message": "Comic Diary vault created!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken."}), 409
    finally:
        conn.close()

@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    try:
        data  = request.get_json(force=True, silent=True) or {}
        email = data.get("email", "").strip().lower()
        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required."}), 400
        
        code = str(random.randint(100000, 999999))
        otp_store[f"email:{email}"] = code
        email_ok, smtp_detail = _send_email_otp(email, code)
        
        dev_mode = not bool(SMTP_USER and SMTP_PASS)
        resp = {
            "status": "Success",
            "message": f"Verification code dispatched to {email}.",
            "dev_mode": dev_mode,
            "smtp_debug": smtp_detail
        }
        if dev_mode or not email_ok:
            resp["otp"] = code
        return jsonify(resp)
    except Exception as err:
        print(f"[REQUEST_OTP ERROR]: {err}")
        traceback.print_exc()
        return jsonify({"error": f"Backend Error: {str(err)}"}), 400

@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip().lower()
    code  = data.get("code", "").strip()
    if otp_store.get(f"email:{email}") != code:
        return jsonify({"error": "Invalid or expired OTP."}), 401
    otp_store[f"verified:email:{email}"] = True
    return jsonify({"status": "Success", "message": "Code verified!"})

@app.route("/api/auth/register-identity", methods=["POST"])
def register_identity():
    data     = request.get_json(force=True, silent=True) or {}
    email    = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not all([email, username, password]):
        return jsonify({"error": "All fields are required."}), 400
    if not otp_store.get(f"verified:email:{email}"):
        return jsonify({"error": "Email not verified."}), 403
    p_hash       = hash_password(password)
    username_key = username.lower()
    initial_seed = _build_initial_seed()
    conn   = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username_key, p_hash)
        )
        cursor.execute(
            "INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)",
            (username_key, json.dumps(initial_seed))
        )
        conn.commit()
        otp_store.pop(f"email:{email}", None)
        otp_store.pop(f"verified:email:{email}", None)
        return jsonify({
            "status":      "Success",
            "username":    username,
            "avatar_desc": "programmer in minimalist hoodie, sleek glasses",
            "global_alignments": {},
            "fs_tree":     initial_seed
        }), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken."}), 409
    finally:
        conn.close()

@app.route("/api/login", methods=["POST"])
def verify_vault_access():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error": "Missing credentials."}), 400
    p_hash       = hash_password(password)
    username_key = username.lower()
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password_hash, avatar_desc, global_alignments FROM users WHERE username = ?",
        (username_key,)
    )
    row = cursor.fetchone()
    if not row or row[0] != p_hash:
        conn.close()
        return jsonify({"error": "Invalid credentials."}), 401
    cursor.execute(
        "SELECT fs_tree_json FROM file_systems WHERE username = ?",
        (username_key,)
    )
    fs_row = cursor.fetchone()
    conn.close()
    fs_tree           = json.loads(fs_row[0]) if fs_row else []
    global_alignments = json.loads(row[2] or "{}") if row[2] else {}
    return jsonify({
        "status":            "Success",
        "username":          username,
        "avatar_desc":       row[1],
        "global_alignments": global_alignments,
        "fs_tree":           fs_tree
    })

@app.route("/api/save", methods=["POST"])
def commit_matrix_state():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username")
    fs_tree  = data.get("fs_tree")
    if not username or fs_tree is None:
        return jsonify({"error": "username and fs_tree are required."}), 400
    username_key      = username.lower()
    avatar_desc       = data.get("avatar_desc", "programmer in minimalist hoodie, sleek glasses")
    global_alignments = data.get("global_alignments", {})
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username = ?", (username_key,))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE users SET avatar_desc = ?, global_alignments = ? WHERE username = ?",
            (avatar_desc, json.dumps(global_alignments), username_key)
        )
    else:
        cursor.execute(
            "INSERT INTO users (username, password_hash, avatar_desc, global_alignments) VALUES (?, ?, ?, ?)",
            (username_key, hash_password("changeme"), avatar_desc, json.dumps(global_alignments))
        )
    cursor.execute("SELECT username FROM file_systems WHERE username = ?", (username_key,))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE file_systems SET fs_tree_json = ? WHERE username = ?",
            (json.dumps(fs_tree), username_key)
        )
    else:
        cursor.execute(
            "INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)",
            (json.dumps(fs_tree))
        )
    conn.commit()
    conn.close()
    return jsonify({"status": "Success", "message": "State permanently saved."})

@app.route("/api/entry/characters", methods=["POST"])
def update_entry_characters():
    data       = request.get_json(force=True, silent=True) or {}
    username   = data.get("username")
    file_id    = data.get("file_id")
    characters = data.get("characters")
    if not username or not file_id or characters is None:
        return jsonify({"error": "username, file_id, and characters are required."}), 400
    username_key = username.lower()
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username = ?", (username_key,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "User file system not found."}), 404
    fs_tree = json.loads(row[0])
    updated = _patch_file_characters(fs_tree, file_id, characters)
    if not updated:
        conn.close()
        return jsonify({"error": f"File id '{file_id}' not found in tree."}), 404
    cursor.execute("UPDATE file_systems SET fs_tree_json = ? WHERE username = ?", (json.dumps(fs_tree), username_key))
    conn.commit()
    conn.close()
    return jsonify({"status": "Success", "message": f"Characters for entry '{file_id}' saved."})

def _patch_file_characters(tree: list, target_id: str, characters: list) -> bool:
    for node in tree:
        if node.get("type") == "file" and node.get("id") == target_id:
            node["characters"] = characters
            return True
        if node.get("type") == "folder":
            if _patch_file_characters(node.get("children", []), target_id, characters):
                return True
    return False

@app.route("/api/alignments", methods=["GET"])
def get_global_alignments():
    username = request.args.get("username", "").strip().lower()
    if not username:
        return jsonify({"error": "username is required."}), 400
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT avatar_desc, global_alignments FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"status": "Success", "avatar_desc": row[0], "global_alignments": json.loads(row[1] or "{}")})

@app.route("/api/alignments", methods=["POST"])
def update_global_alignments():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip().lower()
    if not username:
        return jsonify({"error": "username is required."}), 400
    avatar_desc       = data.get("avatar_desc")
    global_alignments = data.get("global_alignments", {})
    conn   = _get_conn()
    cursor = conn.cursor()
    updates = ["global_alignments = ?"]
    params  = [json.dumps(global_alignments)]
    if avatar_desc is not None:
        updates.append("avatar_desc = ?")
        params.append(avatar_desc)
    params.append(username)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE username = ?", params)
    conn.commit()
    conn.close()
    return jsonify({"status": "Success", "message": "Global alignments updated."})

@app.route("/api/render-comic", methods=["POST"])
def process_cached_artwork_panel():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username")
    optimized_prompt   = data.get("prompt", "")
    content            = data.get("content", "")
    mood               = data.get("mood", "😊")
    image_seed         = data.get("image_seed")
    entry_characters   = data.get("entry_characters", [])   
    avatar_desc        = data.get("avatar_desc", "")
    global_alignments  = data.get("global_alignments", {})
    if not optimized_prompt:
        return jsonify({"error": "prompt cannot be empty."}), 400
    if username and (not avatar_desc or not global_alignments):
        conn   = _get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_desc, global_alignments FROM users WHERE username = ?", (username.lower(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            avatar_desc       = avatar_desc or row[0] or ""
            stored_globals    = json.loads(row[1] or "{}")
            if not global_alignments:
                global_alignments = stored_globals
    char_guidelines = _build_char_guidelines(avatar_desc, global_alignments, entry_characters)
    api_key      = os.environ.get("GEMINI_API_KEY", "")
    refined_prompt = optimized_prompt
    if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
        refined_prompt = _refine_with_gemini(api_key, optimized_prompt, char_guidelines, mood, content, image_seed)
    char_list = []
    if avatar_desc:
        char_list.append(f"Main: {avatar_desc}")
    for align_key in ("father", "mother", "others"):
        val = global_alignments.get(align_key, "")
        if val:
            char_list.append(f"{align_key.capitalize()}: {val}")
    for ec in entry_characters:
        name = ec.get("name", "")
        role = ec.get("role", "")
        desc = ec.get("desc", ec.get("description", ""))
        if name:
            char_list.append(f"{name} ({role}): {desc}" if role else f"{name}: {desc}")
    characters_focus = f"With characters — {'; '.join(char_list)}. " if char_list else ""
    final_art_prompt = (
        f"{characters_focus}{refined_prompt}. "
        "Stylized 2D graphic novel comic art cell. Clean high-contrast colors, crisp ink outline work."
    )
    rand_seed = random.randint(1, 1_000_000)
    api_url   = f"https://image.pollinations.ai/prompt/{requests.utils.quote(final_art_prompt)}?width=512&height=512&nologo=true&seed={rand_seed}"
    try:
        resp = requests.get(api_url, timeout=25)
        if resp.status_code == 200 and len(resp.content) > 1000:
            b64  = base64.b64encode(resp.content).decode("utf-8")
            return jsonify({"status": "Success", "image_data_url": f"data:image/png;base64,{b64}", "optimized_prompt": final_art_prompt})
    except Exception as e:
        print(f"[Pollinations] error: {e}")
    svg_b64 = _build_svg_fallback(mood, content, avatar_desc, global_alignments.get("father", ""), global_alignments.get("mother", ""), global_alignments.get("others", ""), entry_characters)
    return jsonify({"status": "Success", "image_data_url": svg_b64, "optimized_prompt": final_art_prompt, "fallback": True})

def _build_char_guidelines(avatar_desc, global_alignments, entry_characters):
    parts = []
    if avatar_desc:
        parts.append(f"Self: {avatar_desc}")
    for key in ("father", "mother", "others"):
        val = global_alignments.get(key, "")
        if val:
            parts.append(f"{key.capitalize()}: {val}")
    for ec in entry_characters:
        name = ec.get("name", "")
        role = ec.get("role", "")
        desc = ec.get("desc", ec.get("description", ""))
        if name:
            parts.append(f"{name} ({role}): {desc}" if role else f"{name}: {desc}")
    return ". ".join(parts)

def _refine_with_gemini(api_key, base_prompt, char_guidelines, mood, content, image_seed):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        instructions = f"Create a single visual prompt for a comic panel.\nCharacter guidelines: \"{char_guidelines}\"\nMood: \"{mood}\"\nEntry Content: \"{content}\"\nBase Prompt: \"{base_prompt}\"\n"
        parts = []
        parsed_img = parse_data_url(image_seed) if image_seed else None
        if parsed_img:
            parts.append({"inlineData": {"mimeType": parsed_img["mimeType"], "data": parsed_img["data"]}})
        parts.append({"text": instructions})
        res = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=15)
        if res.status_code == 200:
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text:
                return text
    except Exception as e:
        print(f"[Gemini] error: {e}")
    return base_prompt

def _build_svg_fallback(mood, content, avatar_desc, father_desc, mother_desc, others_desc, entry_characters):
    safe_content = (content[:150] + "...") if content else "Reflective thoughts in progress."
    safe_avatar  = avatar_desc or "Protagonist"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%"><rect width="500" height="500" fill="#000"/><text x="250" y="250" font-family="sans-serif" font-size="20" text-anchor="middle" fill="#FFF">{safe_avatar}</text></svg>"""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"

@app.route("/api/delete-account", methods=["POST"])
def delete_account():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error": "username and password are required."}), 400
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    if not row or row[0] != hash_password(password):
        conn.close()
        return jsonify({"error": "Invalid credentials."}), 401
    cursor.execute("DELETE FROM file_systems WHERE username = ?", (username,))
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return jsonify({"status": "Success", "message": "Account deleted."})

@app.route("/api/messenger/request-otp", methods=["POST"])
def request_messenger_otp():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email", "").strip() or "user@messenger.io"
    code = str(random.randint(100000, 999999))
    otp_store[f"email:{email}"] = code
    _send_email_otp(email, code)
    return jsonify({"status": "Success", "message": "OTP dispatched.", "debug_otp": code})

@app.route("/api/messenger/verify-otp", methods=["POST"])
def verify_messenger_otp():
    data   = request.get_json(force=True, silent=True) or {}
    email  = data.get("email", "").strip()
    code   = data.get("code", "").strip()
    stored = otp_store.get(f"email:{email}")
    if not stored or stored != code:
        return jsonify({"error": "Invalid OTP."}), 401
    return jsonify({"status": "Success", "message": "Verified!"})

def _build_initial_seed():
    return [{"id": "fold_seed_1", "type": "folder", "name": "Comic Diary Logs 📒", "children": [{"id": "file_seed_1", "type": "file", "name": "Inaugural Entry", "content": "Welcome!", "mood": "😊", "created": "6/27/2026", "edited": "6/27/2026", "comic": "", "stickers": [], "characters": []}]}]

if __name__ == "__main__":
    app.run(debug=True, port=5000)