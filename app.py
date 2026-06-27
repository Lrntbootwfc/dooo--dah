import os
import json
import base64
import sqlite3
import hashlib
import random
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
# ─── STORAGE SETUP ───
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "vault_storage")
COMICS_DIR  = os.path.join(STORAGE_DIR, "generated_comics")
DB_PATH     = os.path.join(STORAGE_DIR, "chronicle_vault.db")
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(COMICS_DIR,  exist_ok=True)
# ─── DATABASE INIT ───────────────────────────────────────────────────────────
def init_db():
    """
    Schema:
      users        – login credentials + permanent global alignments (JSON)
      file_systems – the full fs_tree per user (files carry per-entry characters)
      otp_verifications – OTP codes
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # ① Users — stores permanent global alignments as JSON blob
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username          TEXT PRIMARY KEY,
            password_hash     TEXT NOT NULL,
            avatar_desc       TEXT DEFAULT 'programmer in minimalist hoodie, sleek glasses',
            global_alignments TEXT DEFAULT '{}'
        )
    ''')
    # ② File-system tree (per user)  — fs_tree_json embeds per-entry characters
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_systems (
            username     TEXT PRIMARY KEY,
            fs_tree_json TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    # ③ OTP verification
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS otp_verifications (
            target     TEXT PRIMARY KEY,
            otp_code   TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Migration: add global_alignments column if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN global_alignments TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass   # column already exists
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
# ─── OTP INFRASTRUCTURE ──────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", os.environ.get("SMTP_SERVER", "smtp.gmail.com"))
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", os.environ.get("SMTP_USERNAME", ""))
SMTP_PASS = os.environ.get("SMTP_PASS", os.environ.get("SMTP_PASSWORD", ""))
otp_store: dict = {}
def _send_email_otp(to_email: str, code: str) -> bool:
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
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_USER, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                    server.sendmail(SMTP_USER, [to_email], msg.as_string())
            print(f"[SMTP SUCCESS] Real OTP sent to {to_email}")
            return True
        except Exception as e:
            print(f"[SMTP ERROR] Failed sending to {to_email}: {e}")
            return False
    print(f"[DEV FALLBACK] OTP for {to_email}: {code}")
    return False
# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════════
# ── ROUTE 1a: Legacy signup ──────────────────────────────────────────────────
@app.route("/api/signup", methods=["POST"])
def register_vault_identity():
    data     = request.json or {}
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
        return jsonify({"status": "Success",
                        "message": "Comic Diary vault created!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken."}), 409
    finally:
        conn.close()
# ── ROUTE 1b: OTP – request ──────────────────────────────────────────────────
@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    data  = request.json or {}
    email = data.get("email", "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "A valid email is required."}), 400
    code = str(random.randint(100000, 999999))
    otp_store[f"email:{email}"] = code
    email_ok = _send_email_otp(email, code)
    dev_mode = not bool(SMTP_USER and SMTP_PASS)
    resp = {"status": "Success",
            "message": f"Verification code dispatched to {email}.",
            "dev_mode": dev_mode}
    if dev_mode or not email_ok:
        resp["otp"] = code
    return jsonify(resp)
# ── ROUTE 1c: OTP – verify ───────────────────────────────────────────────────
@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data  = request.json or {}
    email = data.get("email", "").strip().lower()
    code  = data.get("code", "").strip()
    if otp_store.get(f"email:{email}") != code:
        return jsonify({"error": "Invalid or expired OTP."}), 401
    otp_store[f"verified:email:{email}"] = True
    return jsonify({"status": "Success", "message": "Code verified!"})
# ── ROUTE 1d: Register identity (post-OTP) ───────────────────────────────────
@app.route("/api/auth/register-identity", methods=["POST"])
def register_identity():
    data     = request.json or {}
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
# ── ROUTE 2: Login ───────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def verify_vault_access():
    data     = request.json or {}
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
# ═══════════════════════════════════════════════════════════════════════════════
#  CORE SAVE  ──  AUTO-SAVE + PERMANENT STORAGE
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/save", methods=["POST"])
def commit_matrix_state():
    """
    Persists the entire user state permanently.
    """
    data     = request.json or {}
    username = data.get("username")
    fs_tree  = data.get("fs_tree")
    if not username or fs_tree is None:
        return jsonify({"error": "username and fs_tree are required."}), 400
    username_key      = username.lower()
    avatar_desc       = data.get("avatar_desc", "programmer in minimalist hoodie, sleek glasses")
    global_alignments = data.get("global_alignments", {})
    conn   = _get_conn()
    cursor = conn.cursor()
    # Upsert users row
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
    # Upsert file_systems row
    cursor.execute("SELECT username FROM file_systems WHERE username = ?", (username_key,))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE file_systems SET fs_tree_json = ? WHERE username = ?",
            (json.dumps(fs_tree), username_key)
        )
    else:
        cursor.execute(
            "INSERT INTO file_systems (username, fs_tree_json) VALUES (?, ?)",
            (username_key, json.dumps(fs_tree))
        )
    conn.commit()
    conn.close()
    return jsonify({
        "status":  "Success",
        "message": "State permanently saved."
    })
# ═══════════════════════════════════════════════════════════════════════════════
#  PER-ENTRY CHARACTER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/entry/characters", methods=["POST"])
def update_entry_characters():
    data       = request.json or {}
    username   = data.get("username")
    file_id    = data.get("file_id")
    characters = data.get("characters")
    if not username or not file_id or characters is None:
        return jsonify({"error": "username, file_id, and characters are required."}), 400
    username_key = username.lower()
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT fs_tree_json FROM file_systems WHERE username = ?",
        (username_key,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "User file system not found."}), 404
    fs_tree = json.loads(row[0])
    updated = _patch_file_characters(fs_tree, file_id, characters)
    if not updated:
        conn.close()
        return jsonify({"error": f"File id '{file_id}' not found in tree."}), 404
    cursor.execute(
        "UPDATE file_systems SET fs_tree_json = ? WHERE username = ?",
        (json.dumps(fs_tree), username_key)
    )
    conn.commit()
    conn.close()
    return jsonify({
        "status":  "Success",
        "message": f"Characters for entry '{file_id}' saved."
    })
def _patch_file_characters(tree: list, target_id: str, characters: list) -> bool:
    for node in tree:
        if node.get("type") == "file" and node.get("id") == target_id:
            node["characters"] = characters
            return True
        if node.get("type") == "folder":
            if _patch_file_characters(node.get("children", []), target_id, characters):
                return True
    return False
# ═══════════════════════════════════════════════════════════════════════════════
#  GLOBAL ALIGNMENTS  (permanent baseline)
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/alignments", methods=["GET"])
def get_global_alignments():
    username = request.args.get("username", "").strip().lower()
    if not username:
        return jsonify({"error": "username is required."}), 400
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT avatar_desc, global_alignments FROM users WHERE username = ?",
        (username,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "User not found."}), 404
    return jsonify({
        "status":            "Success",
        "avatar_desc":       row[0],
        "global_alignments": json.loads(row[1] or "{}")
    })
@app.route("/api/alignments", methods=["POST"])
def update_global_alignments():
    data     = request.json or {}
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
    cursor.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE username = ?",
        params
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "Success", "message": "Global alignments updated."})
# ═══════════════════════════════════════════════════════════════════════════════
#  COMIC GENERATION  –  merges entry content + per-entry chars + global aligns
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/render-comic", methods=["POST"])
def process_cached_artwork_panel():
    data     = request.json or {}
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
        cursor.execute(
            "SELECT avatar_desc, global_alignments FROM users WHERE username = ?",
            (username.lower(),)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            avatar_desc       = avatar_desc or row[0] or ""
            stored_globals    = json.loads(row[1] or "{}")
            if not global_alignments:
                global_alignments = stored_globals
    char_guidelines = _build_char_guidelines(
        avatar_desc, global_alignments, entry_characters
    )
    api_key      = os.environ.get("GEMINI_API_KEY", "")
    refined_prompt = optimized_prompt
    if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
        refined_prompt = _refine_with_gemini(
            api_key, optimized_prompt, char_guidelines, mood, content, image_seed
        )
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
        "Stylized 2D graphic novel comic art cell. Clean high-contrast colors, "
        "crisp ink outline work. No lettering, no speech bubbles."
    )
    rand_seed = random.randint(1, 1_000_000)
    api_url   = (
        f"https://image.pollinations.ai/prompt/{requests.utils.quote(final_art_prompt)}"
        f"?width=512&height=512&nologo=true&seed={rand_seed}"
    )
    try:
        resp = requests.get(api_url, timeout=25)
        if resp.status_code == 200 and len(resp.content) > 1000:
            b64  = base64.b64encode(resp.content).decode("utf-8")
            return jsonify({
                "status":          "Success",
                "image_data_url":  f"data:image/png;base64,{b64}",
                "optimized_prompt": final_art_prompt
            })
    except Exception as e:
        print(f"[Pollinations] error: {e} – using SVG fallback")
    svg_b64 = _build_svg_fallback(
        mood, content, avatar_desc,
        global_alignments.get("father", ""),
        global_alignments.get("mother", ""),
        global_alignments.get("others", ""),
        entry_characters
    )
    return jsonify({
        "status":          "Success",
        "image_data_url":  svg_b64,
        "optimized_prompt": final_art_prompt,
        "fallback":        True
    })
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
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.5-flash:generateContent?key={api_key}"
        )
        instructions = (
            "Create a single highly descriptive, compressed visual prompt for an image "
            "generator to create a 2D comic panel.\n"
            f"Character guidelines: \"{char_guidelines}\"\n"
            f"Mood: \"{mood}\"\n"
            f"Entry Content: \"{content}\"\n"
            f"Base Prompt: \"{base_prompt}\"\n"
        )
        if image_seed:
            instructions += (
                "\nA doodle/canvas sketch is attached. Incorporate its visual layout "
                "directly into the refined description."
            )
        instructions += (
            "\n\nFocus on visual layout, setting, lighting, character pose, and clean "
            "indie comic-book sketch style. No speech bubbles, no text lettering, no markdown. "
            "Output ONLY the refined visual prompt text."
        )
        parts = []
        parsed_img = parse_data_url(image_seed) if image_seed else None
        if parsed_img:
            parts.append({"inlineData": {"mimeType": parsed_img["mimeType"],
                                          "data": parsed_img["data"]}})
        parts.append({"text": instructions})
        res = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=15)
        if res.status_code == 200:
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text:
                return text
    except Exception as e:
        print(f"[Gemini] refinement failed: {e}")
    return base_prompt
def _build_svg_fallback(mood, content, avatar_desc, father_desc, mother_desc,
                         others_desc, entry_characters):
    safe_content = (content[:150] + "...") if content else "Reflective thoughts in progress."
    safe_avatar  = avatar_desc or "Protagonist"
    safe_father  = father_desc or ""
    safe_mother  = mother_desc or ""
    safe_others  = others_desc or ""
    color_themes = {
        "😊": {"bg": "#FFFbeb", "accent": "#F59e0b", "text": "#78350f"},
        "💻": {"bg": "#ECfeff", "accent": "#06b6d4", "text": "#164e63"},
        "🌌": {"bg": "#FAF5ff", "accent": "#8b5cf6", "text": "#4c1d95"},
        "⚡": {"bg": "#FEf2f2", "accent": "#ef4444", "text": "#7f1d1d"},
    }
    theme = color_themes.get(mood, {"bg": "#F8fafc", "accent": "#64748b", "text": "#0f172a"})
    ec_rows = ""
    for i, ec in enumerate(entry_characters[:4]):
        y = 230 + i * 22
        name = ec.get("name", "")[:18]
        role = ec.get("role", "")[:16]
        if name:
            ec_rows += (
                f'<text x="20" y="{y}" font-family="sans-serif" font-size="9" '
                f'font-weight="bold" fill="#0F172A">{name}</text>'
                f'<text x="110" y="{y}" font-family="sans-serif" font-size="8" '
                f'fill="#64748B">{role}</text>'
            )
    father_block = f"""
        <circle cx="35" cy="125" r="20" fill="{theme['accent']}" opacity="0.2" stroke="#000" stroke-width="1.5"/>
        <text x="35" y="130" font-family="sans-serif" font-size="14" text-anchor="middle">👨</text>
        <text x="65" y="120" font-family="sans-serif" font-weight="bold" font-size="10" fill="#000">FATHER</text>
        <text x="65" y="133" font-family="sans-serif" font-size="8.5" fill="#475569">{safe_father[:24]}</text>
    """ if safe_father else f"""
        <circle cx="35" cy="125" r="20" fill="#F1F5F9" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="3 3"/>
        <text x="35" y="130" font-family="sans-serif" font-size="12" text-anchor="middle" fill="#94A3B8">?</text>
        <text x="65" y="128" font-family="sans-serif" font-size="9" fill="#94A3B8" font-style="italic">Father not set</text>
    """
    mother_block = f"""
        <circle cx="35" cy="180" r="20" fill="{theme['accent']}" opacity="0.2" stroke="#000" stroke-width="1.5"/>
        <text x="35" y="185" font-family="sans-serif" font-size="14" text-anchor="middle">👩</text>
        <text x="65" y="175" font-family="sans-serif" font-weight="bold" font-size="10" fill="#000">MOTHER</text>
        <text x="65" y="188" font-family="sans-serif" font-size="8.5" fill="#475569">{safe_mother[:24]}</text>
    """ if safe_mother else f"""
        <circle cx="35" cy="180" r="20" fill="#F1F5F9" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="3 3"/>
        <text x="35" y="185" font-family="sans-serif" font-size="12" text-anchor="middle" fill="#94A3B8">?</text>
        <text x="65" y="183" font-family="sans-serif" font-size="9" fill="#94A3B8" font-style="italic">Mother not set</text>
    """
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <rect width="500" height="500" fill="#000"/>
  <g transform="translate(15,15)">
    <rect width="200" height="85" fill="#FFFFFF" stroke="#000" stroke-width="3" rx="6"/>
    <circle cx="35" cy="42" r="24" fill="{theme['accent']}" opacity="0.25"/>
    <text x="35" y="50" font-family="sans-serif" font-size="22" text-anchor="middle">🧑</text>
    <text x="70" y="32" font-family="sans-serif" font-weight="bold" font-size="11" fill="#000">SELF</text>
    <text x="70" y="46" font-family="sans-serif" font-size="8.5" fill="#475569">{safe_avatar[:26]}</text>
  </g>
  <g transform="translate(15,110)">
    <rect width="200" height="200" fill="#FFFFFF" stroke="#000" stroke-width="3" rx="6"/>
    <text x="100" y="22" font-family="monospace" font-weight="bold" font-size="10" text-anchor="middle" fill="#0F172A">GLOBAL ALIGNMENTS</text>
    {father_block}
    {mother_block}
  </g>
  <g transform="translate(230,15)">
    <rect width="255" height="295" fill="#FFFFFF" stroke="#000" stroke-width="3" rx="6"/>
    <text x="127" y="22" font-family="monospace" font-weight="bold" font-size="10" text-anchor="middle" fill="#0F172A">ENTRY CHARACTERS</text>
    <line x1="10" y1="28" x2="245" y2="28" stroke="#E2E8F0" stroke-width="1"/>
    {'<text x="127" y="130" font-family="sans-serif" font-size="9" text-anchor="middle" fill="#94A3B8" font-style="italic">No entry characters yet</text>' if not entry_characters else ec_rows}
  </g>
  <g transform="translate(15,325)">
    <rect width="470" height="160" fill="#FFFFFF" stroke="#000" stroke-width="3" rx="6"/>
    <text x="235" y="22" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle" fill="#0F172A">Daily Comic Sketch</text>
    <rect x="10" y="30" width="450" height="115" fill="{theme['bg']}" stroke="#000" stroke-width="1.5" rx="4"/>
    <text x="20" y="50" font-family="monospace" font-size="10" fill="{theme['text']}">{safe_content[:60]}</text>
  </g>
  <rect x="170" y="460" width="160" height="25" fill="#000"/>
  <text x="250" y="477" font-family="monospace" font-weight="bold" font-size="11" text-anchor="middle" fill="#FFF">PANEL GENERATED</text>
</svg>"""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"
# ═══════════════════════════════════════════════════════════════════════════════
#  ACCOUNT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/delete-account", methods=["POST"])
def delete_account():
    data     = request.json or {}
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
# ═══════════════════════════════════════════════════════════════════════════════
#  LEGACY MESSENGER OTP COMPAT
# ═══════════════════════════════════════════════════════════════════════════════
@app.route("/api/messenger/request-otp", methods=["POST"])
def request_messenger_otp():
    data  = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        email = "user@messenger.io"
    code = str(random.randint(100000, 999999))
    otp_store[f"email:{email}"] = code
    _send_email_otp(email, code)
    return jsonify({"status": "Success",
                    "message": "OTP dispatched.",
                    "debug_otp": code})
@app.route("/api/messenger/verify-otp", methods=["POST"])
def verify_messenger_otp():
    data   = request.json or {}
    email  = data.get("email", "").strip()
    code   = data.get("code", "").strip()
    stored = otp_store.get(f"email:{email}")
    if not stored or stored != code:
        return jsonify({"error": "Invalid OTP."}), 401
    return jsonify({"status": "Success", "message": "Verified!"})
def _build_initial_seed():
    return [{
        "id": "fold_seed_1", "type": "folder", "name": "Comic Diary Logs 📒",
        "children": [{
            "id": "file_seed_1", "type": "file", "name": "Inaugural Entry",
            "content": "Welcome to my encrypted Comic Diary! Today I am sketching out ideas for our first graphic novel.",
            "mood": "😊",
            "created": "6/27/2026, 9:00 AM",
            "edited":  "6/27/2026, 9:00 AM",
            "comic": "",
            "stickers": [],
            "characters": []
        }]
    }]
if __name__ == "__main__":
    app.run(debug=True, port=5000)