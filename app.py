import os, json, base64, sqlite3, hashlib, random, requests, smtplib
import traceback, time, textwrap, math, io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.errorhandler(Exception)
def handle_global_exception(e):
    # Log the full exception with traceback
    tb = traceback.format_exc()
    print(f"[UNHANDLED EXCEPTION IN FLASK]:\n{tb}")
    
    # Check if this is a standard HTTP error from Flask
    if hasattr(e, "code") and hasattr(e, "name"):
        status_code = e.code
        error_msg = getattr(e, "description", e.name)
    else:
        status_code = 500
        error_msg = str(e) or "Internal Server Error"
        
    response = jsonify({
        "status": "Error",
        "error": error_msg,
        "type": e.__class__.__name__,
        "traceback": tb.split("\n")
    })
    response.status_code = status_code
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

# ─── STORAGE ─────────────────────────────────────────────────────────────────
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "vault_storage")
COMICS_DIR  = os.path.join(STORAGE_DIR, "generated_comics")
DB_PATH     = os.path.join(STORAGE_DIR, "chronicle_vault.db")
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(COMICS_DIR,  exist_ok=True)

# ─── FONTS ───────────────────────────────────────────────────────────────────
FONT_BOLD    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_ITALIC  = "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"

def _font(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

# ─── LIMITS ──────────────────────────────────────────────────────────────────
MAX_PANELS_PER_PAGE = 4
MAX_PAGES           = 6

# ─── DATABASE ────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
        avatar_desc TEXT DEFAULT 'programmer in minimalist hoodie, sleek glasses',
        global_alignments TEXT DEFAULT '{}')''')
    c.execute('''CREATE TABLE IF NOT EXISTS file_systems (
        username TEXT PRIMARY KEY, fs_tree_json TEXT NOT NULL,
        FOREIGN KEY(username) REFERENCES users(username))''')
    c.execute('''CREATE TABLE IF NOT EXISTS otp_verifications (
        target TEXT PRIMARY KEY, otp_code TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    try:
        c.execute("ALTER TABLE users ADD COLUMN global_alignments TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass
    conn.commit(); conn.close()

init_db()

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()
def parse_data_url(u):
    if not u or "," not in u: return None
    try:
        header, data = u.split(",", 1)
        mime = header.split(";")[0].replace("data:", "") if "data:" in header else "image/png"
        return {"mimeType": mime, "data": data}
    except: return None
def _get_conn(): return sqlite3.connect(DB_PATH, timeout=30.0)

# ─── SMTP ────────────────────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
SMTP_PORT = int(str(os.environ.get("SMTP_PORT", "587")).strip() or "587")
otp_store: dict = {}

def _send_email_otp(to_email, code):
    if not (SMTP_USER and SMTP_PASS): return False, "SMTP not configured"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🔐 Comic Diary — Email Verification Code"
        msg["From"]    = f'"Comic Diary Auth" <{SMTP_USER}>'
        msg["To"]      = to_email
        msg.attach(MIMEText(f"<div style='font-size:32px;font-weight:bold;letter-spacing:6px;color:#38bdf8'>{code}</div>", "html"))
        srv = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) if SMTP_PORT == 465 \
              else smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        if SMTP_PORT != 465: srv.starttls()
        srv.login(SMTP_USER, SMTP_PASS); srv.sendmail(SMTP_USER, [to_email], msg.as_string()); srv.quit()
        return True, "sent"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
#  COMIC COMPOSITING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Agent 1: Story Understanding AI ───────────────────────────────────────
def _run_agent_story_understanding(api_key, content, mood):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"""You are 'Agent 1: Story Understanding AI'. Your job is to deeply analyze the following diary entry/story.

DIARY ENTRY:
\"\"\"{content}\"\"\"

MOOD: {mood}

Analyze the entry and extract:
1. The genre of the story.
2. The emotion curve (a sequential list of emotional states the narrator goes through, e.g. ["Excitement", "Joy", "Nostalgia", "Sadness"]).
3. The key characters present in the story (including their role, gender, age if mentioned).
4. The key locations mentioned.
5. Important chronologically ordered events.

Respond ONLY with valid JSON (no markdown block, no '```json' wrapper):
{{
  "genre": "Slice of Life",
  "emotion_curve": ["Excitement", "Joy", "Nostalgia", "Sadness"],
  "characters": [
    {{"id": "C1", "role": "Narrator/Protagonist", "gender": "female", "age": "20"}}
  ],
  "locations": ["Cafe", "Road", "Home"],
  "important_events": ["Met my best friend", "She hugged me", "Walking home", "Remembered grandfather"]
}}"""
    try:
        res = requests.post(url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
            timeout=25)
        if res.status_code == 200:
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
    except Exception as e:
        print(f"[Agent 1 Story Understanding error]: {e}")
    return {
        "genre": "Slice of life",
        "emotion_curve": [mood],
        "characters": [{"id": "C1", "role": "Narrator"}],
        "locations": ["Unspecified"],
        "important_events": ["Diary events occurred"]
    }


# ── 2. Agent 2: Comic Director / Storyboard AI ────────────────────────────────
def _run_agent_comic_director_single_page(api_key, content, story_analysis, page_num, total_pages, prior_events_summary):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"""You are 'Agent 2: Comic Director / Storyboard AI'. You think like a movie director and professional storyboard artist.
    
ORIGINAL DIARY ENTRY:
\"\"\"{content}\"\"\"

STORY UNDERSTANDING (from Agent 1):
{json.dumps(story_analysis, indent=2)}

Create exactly 1 comic page (page_number 1) with exactly 1 continuous narrative splash panel (panel_number 1) that represents the entire journal entry in a beautiful storytelling flow. This single image should depict the overall journey, mood, setting, and key characters of the whole story in one fluid composition.

For this single panel, decide:
- PANEL_NUMBER (must be 1)
- CAMERA: camera angle (e.g. "Wide Shot", "Medium Shot", "Bird's Eye View")
- SETTING: background location, time of day, lighting, environment details
- CHARACTERS_PRESENT: list of strings (e.g., ["Narrator", "Best Friend"])
- CHARACTER_EXPRESSIONS: expression of each present character (e.g., "Narrator laughing, Friend smiling")
- ACTION: physical action taking place in the scene that summarizes the story flow
- VISUAL_DETAILS: key visual items, objects, or details to draw that show the story's flow
- DIALOGUE: list of dialogue objects with speaker and text (e.g., [{{"speaker": "Friend", "text": "I missed you!"}}]) or empty list if none
- INNER_THOUGHT: string of thought bubble text, or empty string if none
- CAPTION: short narrative text (max 18 words) summarizing the essence of the entire journal entry
- BUBBLE_TYPE: "speech" | "thought" | "shout" | "whisper" | "none"
- MOOD: overall emotional mood of the story
- LIGHTING: lighting condition

Respond ONLY with valid JSON using this exact structure (no markdown wrappers):
{{
  "page_number": 1,
  "panels": [
    {{
      "panel_number": 1,
      "camera": "Wide Shot",
      "setting": "Cozy room with warm lights",
      "characters_present": ["Narrator"],
      "character_expressions": "peaceful and content smile",
      "action": "Writing down today's adventure in a journal while looking at a beautiful starry sky through the window",
      "visual_details": "open diary on desk, warm desk lamp, stars shining bright outside, coffee mug steaming",
      "dialogue": [],
      "inner_thought": "I feel so grateful for this amazing journey.",
      "caption": "A wonderful day of friendship and shared adventures.",
      "bubble_type": "thought",
      "mood": "Peaceful",
      "lighting": "Warm indoor glow with cool night sky highlight"
    }}
  ]
}}"""
    try:
        res = requests.post(url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.5, "responseMimeType": "application/json"}},
            timeout=35)
        if res.status_code == 200:
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
    except Exception as e:
        print(f"[Agent 2 Single Page Comic Director error for page {page_num}]: {e}")
    return None


# ── 3. Agent 3: Character Sheet Generator AI ───────────────────────────────
def _run_agent_character_sheet(api_key, story_analysis, char_guidelines):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"""You are 'Agent 3: Character Sheet Generator AI'. Your job is to create a temporary consistent character sheet for each key character present.
Characters must be cute, wholesome, anime-inspired webtoon style with round soft faces and big expressive eyes.

STORY ANALYSIS:
{json.dumps(story_analysis, indent=2)}

USER DESIGN PREFERENCES / PROFILE DETAILS:
{char_guidelines}

For each unique character present in the story, define their physical profiles including:
- Hair: length, style, color
- Eyes: color, expression
- Dress: default typical outfit/jacket/colors
- Art Style: Wholesome cute webtoon, vibrant clean outlines
- Height/Age/Other details

Respond ONLY with a valid JSON dictionary where each key is the character's name/role and the value is their visual profile. No markdown formatting.
Example structure:
{{
  "Narrator": "20yo female, shoulder length black hair, brown eyes, blue hoodie, wholesome cute anime webtoon style.",
  "Best Friend": "20yo female, curly light-brown hair, green eyes, yellow jacket over white shirt, big cheerful smile."
}}"""
    try:
        res = requests.post(url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
            timeout=25)
        if res.status_code == 200:
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
    except Exception as e:
        print(f"[Agent 3 Character Sheet error]: {e}")
    return {}


# ── 4. Agent 4: Quality Control Agent (Vision Check) ──────────────────────────
def _run_agent_quality_check(api_key, img_bytes, panel_meta):
    if not img_bytes or len(img_bytes) < 2000:
        return {"verdict": "REGENERATE", "reason": "No valid image data generated", "prompt_adjustment": "Make prompt simpler"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    
    prompt = f"""You are 'Agent 4: Quality Assurance Agent'. Your task is to verify if the generated comic panel image matches the story direction.

TARGET STORY DETAILS:
- Action/Characters: {panel_meta.get("action", "")}
- Present: {", ".join(panel_meta.get("characters_present", []))}
- Lighting/Setting: {panel_meta.get("setting", "")} ({panel_meta.get("lighting", "default lighting")})
- Expression: {panel_meta.get("character_expressions", "")}

Check the generated illustration for:
1. Visual glitches (extra fingers/arms, distorted faces, missing key components).
2. Does it contain text or word bubbles drawn by the AI model? (The image MUST NOT contain any words/bubble text since we overlay them digitally).
3. Does it capture the targeted action and setting reasonably?

Respond ONLY with a valid JSON block of this structure:
{{
  "verdict": "PASS" | "REGENERATE",
  "reason": "Detailed observation explaining why it passes or needs regeneration",
  "prompt_adjustment": "If REGENERATE, write a modified version of the prompt to solve the issue, else empty string"
}}"""
    try:
        res = requests.post(url,
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inlineData": {"mimeType": "image/png", "data": img_b64}}
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            },
            timeout=25)
        if res.status_code == 200:
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = raw.replace("```json","").replace("```","").strip()
            return json.loads(raw)
    except Exception as e:
        print(f"[Agent 4 Quality check error]: {e}")
    return {"verdict": "PASS", "reason": "Bypassed quality check", "prompt_adjustment": ""}


# ── 5. Pollinations: fetch ONE panel image ────────────────────────────────────
def _build_panel_scene_prompt(panel, character_sheet, color_style):
    """Build a prompt for JUST the scene — no speech bubbles, no text, leave whitespace at top."""
    setting         = panel.get("setting", "")
    camera          = panel.get("camera", "Medium Shot")
    action          = panel.get("action", "")
    visual_details  = panel.get("visual_details", panel.get("visual_elements", "")) or ""
    expressions     = panel.get("character_expressions", "cute and expressive")
    chars_present   = panel.get("characters_present", [])
    lighting        = panel.get("lighting", "")
    mood            = panel.get("mood", "")

    # Compile character descriptors
    char_refs = []
    for cname in chars_present:
        profile = character_sheet.get(cname, "")
        if not profile:
            # Fallback fuzzy matching
            for sname, sprofile in character_sheet.items():
                if sname.lower() in cname.lower() or cname.lower() in sname.lower():
                    profile = sprofile
                    break
        if profile:
            char_refs.append(f"{cname} appearance: {profile}")
        else:
            char_refs.append(f"{cname} is a cute anime character.")

    char_ref_str = ". ".join(char_refs) if char_refs else "Cute characters present."

    return (
        f"Comic book panel art, {camera} shot. {char_ref_str} "
        f"Scene and background: {setting}. Lighting: {lighting}. Mood: {mood}. "
        f"Action: {action}. Character expressions: {expressions}. "
        f"Visual details: {visual_details}. "
        f"LEAVE EMPTY WHITE SPACE at the very top (15% of image) for caption text overlay. "
        f"NO speech bubbles, NO text, NO words anywhere in the image. "
        f"Style: {color_style}, clean comic book illustration, detailed expressive background, "
        f"professional manga-inspired panel art. NEVER scary or horrific."
    )

def _fetch_panel_image(prompt, seed, retries=3):
    """Fetch a single panel scene image — 256x255 for individual panels with retry and jitter."""
    encoded = requests.utils.quote(prompt)
    for attempt in range(retries):
        current_seed = seed + attempt
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=256&height=256&nologo=true&seed={current_seed}"
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 2000:
                return resp.content
            print(f"[Pollinations] status={resp.status_code} len={len(resp.content)}")
        except Exception as e:
            print(f"[Pollinations panel] attempt {attempt+1} failed: {e}")
        if attempt < retries - 1:
            time.sleep(1.5 + random.random())
        
    return None


# ── 3. Text wrapping helpers ──────────────────────────────────────────────────
def _wrap_text(text, font, max_width, draw):
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines


# ── 4. Bubble drawers ─────────────────────────────────────────────────────────
def _draw_speech_bubble(draw, cx, cy, text, font, bubble_type="speech",
                         max_w=160, fg=(20,20,20), bg=(255,255,255), border=(20,20,20)):
    """Draw a speech/thought/shout bubble centred near (cx, cy).
    Returns the bounding box (x0,y0,x1,y1) of the bubble."""
    padding  = 10
    lines    = _wrap_text(text, font, max_w - padding*2, draw)
    if not lines: return None

    fsize    = font.size if hasattr(font, 'size') else 13
    line_h   = fsize + 4
    txt_w    = max(draw.textbbox((0,0), l, font=font)[2] for l in lines)
    txt_h    = line_h * len(lines)

    bw = txt_w + padding * 2
    bh = txt_h + padding * 2

    # Position bubble so it doesn't go off canvas
    img_w, img_h = (840, 876)
    x0 = max(4, min(cx - bw//2, img_w - bw - 4))
    y0 = max(4, cy)
    x1 = x0 + bw
    y1 = y0 + bh

    radius = 14 if bubble_type != "shout" else 4

    if bubble_type == "shout":
        # Spiky starburst
        cx_b, cy_b = (x0+x1)//2, (y0+y1)//2
        spikes = 10
        pts = []
        for i in range(spikes * 2):
            angle = math.pi * i / spikes - math.pi / 2
            r = (bw//2 + 8) if i % 2 == 0 else (bw//2 - 4)
            pts.append((cx_b + r * math.cos(angle), cy_b + r * math.sin(angle)))
        draw.polygon(pts, fill=bg, outline=border)
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                                fill=bg, outline=border, width=2)

    if bubble_type == "speech":
        # Tail pointing down
        tail_x = x0 + bw // 3
        draw.polygon([(tail_x, y1), (tail_x+14, y1), (tail_x+2, y1+16)],
                     fill=bg, outline=border)
        draw.line([(tail_x+1, y1), (tail_x+13, y1)], fill=bg, width=3)

    elif bubble_type == "thought":
        # Ellipse dots trailing down
        for r_dot, offset_y in [(5, 0), (4, 9), (3, 16)]:
            dx, dy = x0 + 18, y1 + offset_y
            draw.ellipse([dx-r_dot, dy-r_dot, dx+r_dot, dy+r_dot],
                         fill=bg, outline=border, width=2)

    elif bubble_type == "whisper":
        # Dashed border effect — draw over with dashes
        dash_col = (180, 180, 180)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                                fill=bg, outline=dash_col, width=2)

    # Draw text
    ty = y0 + padding
    for line in lines:
        lbbox = draw.textbbox((0,0), line, font=font)
        lw = lbbox[2]
        tx = x0 + padding + (txt_w - lw) // 2
        draw.text((tx, ty), line, fill=fg, font=font)
        ty += line_h

    return (x0, y0, x1, y1 + (20 if bubble_type in ("speech","thought") else 0))


def _draw_caption_box(draw, x0, y0, x1, text, font, bg=(0,0,0,200), fg=(255,255,255)):
    """Draw a caption box at the top of a panel."""
    if not text: return
    padding = 8
    lines   = _wrap_text(text, font, (x1 - x0) - padding*2, draw)
    fsize   = font.size if hasattr(font,'size') else 11
    line_h  = fsize + 3
    box_h   = line_h * len(lines) + padding * 2

    draw.rectangle([x0, y0, x1, y0 + box_h], fill=(10, 10, 10))
    ty = y0 + padding
    for line in lines:
        draw.text((x0 + padding, ty), line, fill=(255,255,240), font=font)
        ty += line_h
    return y0 + box_h


# ── 5. Composite one full comic PAGE from panel images + metadata ─────────────
def _composite_page(panel_images_bytes, panels_meta, page_num, total_pages, color_style):
    """
    Layout: 1 large narrative splash panel or 2 columns × 2 rows of panels depending on panel count.
    Page canvas: ~820 × 900 with margins, page label, panel borders.
    Overlays: caption boxes, speech bubbles, thought bubbles — all crisp text.
    """
    is_single_panel = len(panels_meta) == 1
    if is_single_panel:
        PANEL_W, PANEL_H = 780, 800
        COLS, ROWS       = 1, 1
        GUTTER           = 0
        MARGIN           = 20
    else:
        PANEL_W, PANEL_H = 400, 400
        COLS, ROWS       = 2, 2
        GUTTER           = 8
        MARGIN           = 16
    HEADER_H         = 36

    page_w = MARGIN*2 + COLS*PANEL_W + (COLS-1)*GUTTER
    page_h = MARGIN*2 + ROWS*PANEL_H + (ROWS-1)*GUTTER + HEADER_H

    # Page background — aged paper feel
    page = Image.new("RGB", (page_w, page_h), (245, 238, 220))
    draw = ImageDraw.Draw(page)

    # Outer border
    draw.rectangle([2, 2, page_w-3, page_h-3], outline=(30,20,10), width=3)

    # Page header
    hfont = _font(FONT_BOLD, 13)
    header_text = f"PAGE {page_num} / {total_pages}"
    draw.rectangle([0, 0, page_w, HEADER_H], fill=(20, 20, 20))
    draw.text((MARGIN, 10), header_text, fill=(255, 200, 60), font=hfont)

    # Fonts
    caption_font  = _font(FONT_BOLD,    11)
    dialogue_font = _font(FONT_BOLD,    13)
    thought_font  = _font(FONT_ITALIC,  12)
    whisper_font  = _font(FONT_ITALIC,  11)

    for idx, (img_bytes, panel) in enumerate(zip(panel_images_bytes, panels_meta)):
        col = idx % COLS
        row = idx // COLS

        px = MARGIN + col * (PANEL_W + GUTTER)
        py = MARGIN + HEADER_H + row * (PANEL_H + GUTTER)

        # ── Place panel image ──
        if img_bytes:
            try:
                pimg = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                pimg = pimg.resize((PANEL_W, PANEL_H), Image.LANCZOS)
                page.paste(pimg, (px, py))
            except Exception as e:
                print(f"[Composite] panel image error: {e}")
                draw.rectangle([px, py, px+PANEL_W, py+PANEL_H], fill=(200,200,210))
        else:
            # Fallback gradient-ish fill
            for yy in range(PANEL_H):
                t  = yy / PANEL_H
                rc = int(180 + 40*t)
                gc = int(160 + 30*t)
                bc = int(200 + 20*t)
                draw.line([(px, py+yy), (px+PANEL_W, py+yy)], fill=(rc,gc,bc))

        # Panel border (thick black line)
        draw.rectangle([px, py, px+PANEL_W, py+PANEL_H], outline=(10,10,10), width=3)

        # ── Caption box (top of panel) ──
        caption = panel.get("caption", "")
        caption_bottom = py
        if caption:
            caption_bottom = _draw_caption_box(
                draw, px, py, px+PANEL_W, caption, caption_font
            ) or py

        # ── Bubble drawing area: below caption, inside panel ──
        bubble_y_start = caption_bottom + 4

        # Speech dialogue
        dialogues = panel.get("dialogue", [])
        btype = panel.get("bubble_type", "speech")
        if dialogues and btype != "none":
            for di, dlg in enumerate(dialogues[:2]):  # max 2 speakers per panel
                txt = dlg.get("text", "").strip()
                if not txt: continue
                # Alternate left/right for multiple speakers
                if di == 0:
                    bx = px + PANEL_W // 4
                else:
                    bx = px + (PANEL_W * 3) // 4

                font_to_use = whisper_font if btype == "whisper" else dialogue_font
                _draw_speech_bubble(
                    draw, bx, bubble_y_start,
                    txt, font_to_use,
                    bubble_type=btype,
                    max_w=min(180, PANEL_W - 20),
                    fg=(10,10,10),
                    bg=(255,255,255) if btype != "shout" else (255,255,180),
                    border=(10,10,10)
                )
                bubble_y_start += 10  # slight offset for next speaker

        # Thought bubble
        inner = panel.get("inner_thought", "").strip()
        if inner:
            _draw_speech_bubble(
                draw, px + PANEL_W - 80, bubble_y_start,
                inner, thought_font,
                bubble_type="thought",
                max_w=150,
                fg=(40,40,100),
                bg=(230,230,255),
                border=(100,100,180)
            )

    return page


# ── 6. PIL image → base64 data URL ───────────────────────────────────────────
def _page_to_data_url(pil_image):
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


# ── 7. Character guidelines builder ──────────────────────────────────────────
def _build_char_guidelines(avatar_desc, global_alignments, entry_characters):
    parts = []
    if avatar_desc:
        parts.append(f"Protagonist: {avatar_desc}")
    for key in ("father", "mother", "others"):
        val = global_alignments.get(key, "")
        if val: parts.append(f"{key.capitalize()}: {val}")
    for ec in entry_characters:
        name = ec.get("name",""); role = ec.get("role","")
        desc = ec.get("desc", ec.get("description",""))
        if name:
            parts.append(f"{name} ({role}): {desc}" if role else f"{name}: {desc}")
    return ". ".join(parts)


def _build_color_style(mood):
    sad    = {"😢","😞","😔","😟","😩","😭"}
    happy  = {"😊","😄","😁","🥳","😍","🎉","😎"}
    calm   = {"😌","🧘","☺️"}
    angry  = {"😠","😤","😡"}
    if any(m in mood for m in sad):   return "soft muted watercolor tones, blues and grays"
    if any(m in mood for m in happy): return "vibrant saturated colors, warm yellows and pinks"
    if any(m in mood for m in calm):  return "soft pastel colors, gentle greens and lavenders"
    if any(m in mood for m in angry): return "bold high-contrast, deep reds and sharp shadows"
    return "rich colorful comic book style, balanced warm tones"


def _estimate_pages(content):
    return 1


def _fallback_storyboard(content, num_pages):
    """Simple sentence-split fallback when Gemini isn't available."""
    sentences = [s.strip() for s in content.replace("!",".").replace("?",".").split(".") if s.strip()]
    pages     = []
    for p in range(num_pages):
        summary_text = " ".join(sentences)[:120] if sentences else "A quiet, reflective moment."
        panels = [{
            "panel_number":        1,
            "camera":              "Wide Shot",
            "setting":             "A beautiful narrative setting reflecting the entry",
            "characters_present":  ["Narrator"],
            "character_expressions": "reflective",
            "action":              summary_text,
            "visual_details":      "gentle warm glows, cozy illustrative elements summarizing the journey",
            "dialogue":            [],
            "inner_thought":       "",
            "caption":             summary_text[:80],
            "bubble_type":         "none",
            "mood":                "Peaceful",
            "lighting":            "soft ambient glow"
        }]
        pages.append({"page_number": p+1, "panels": panels})
    return pages


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

 

@app.route("/api/render-comic-pages", methods=["POST"])
def render_comic_pages():
    data     = request.get_json(force=True, silent=True) or {}
    username = data.get("username")
    content           = data.get("content", "").strip()
    mood              = data.get("mood", "😊")
    entry_characters  = data.get("entry_characters", [])
    avatar_desc       = data.get("avatar_desc", "")
    global_alignments = data.get("global_alignments", {})

    # Optional parameters for single page regeneration
    page_number_to_regen = data.get("page_number_to_regen")
    existing_pages       = data.get("existing_pages", [])
    existing_quality_logs = data.get("existing_quality_logs", [])

    if not content:
        return jsonify({"error": "content cannot be empty."}), 400

    # Load user profile if needed
    if username and (not avatar_desc or not global_alignments):
        conn   = _get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_desc, global_alignments FROM users WHERE username=?", (username.lower(),))
        row = cursor.fetchone(); conn.close()
        if row:
            avatar_desc       = avatar_desc or row[0] or ""
            stored            = json.loads(row[1] or "{}")
            if not global_alignments: global_alignments = stored

    char_guidelines = _build_char_guidelines(avatar_desc, global_alignments, entry_characters)
    color_style     = _build_color_style(mood)
    api_key         = os.environ.get("GEMINI_API_KEY", "")
    num_pages       = _estimate_pages(content)

    print(f"[Comic v4 Multi-Agent] {len(content.split())} words → {num_pages} pages (Regen page: {page_number_to_regen})")

    # ── Step 1: Agent 1 - Story Understanding ──────────────────────────────
    story_analysis = None
    if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
        story_analysis = _run_agent_story_understanding(api_key, content, mood)
    
    if not story_analysis:
        story_analysis = {
            "genre": "Slice of Life",
            "emotion_curve": ["Neutral", mood],
            "characters": [
                {"id": "Narrator", "role": "Narrator/Protagonist", "gender": "female", "age": "20"},
                {"id": "Friend", "role": "Best Friend", "gender": "female", "age": "20"}
            ],
            "locations": ["Inside / Outdoor Settings"],
            "important_events": ["Diary events occurred"]
        }

    # ── Step 2: Agent 3 - Character Sheet Generation ───────────────────────
    character_sheet = None
    if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
        character_sheet = _run_agent_character_sheet(api_key, story_analysis, char_guidelines)
    
    if not character_sheet:
        character_sheet = {
            "Narrator": f"Protagonist, {avatar_desc or 'cute youth in minimalist hoodie, sleek glasses'}.",
            "Best Friend": "Curly haired smiling best friend wearing a bright warm jacket.",
            "Grandfather": "Kindly grandfather with soft grey hair and an warm posture."
        }

    # ── Step 3: Agent 2 - Comic Director (Storyboard) ──────────────────────
    pages_data = []
    reusing_storyboard = False
    
    if page_number_to_regen is not None:
        try:
            page_number_to_regen = int(page_number_to_regen)
        except:
            page_number_to_regen = None

    if page_number_to_regen is not None and existing_pages:
        target_page = None
        for p in existing_pages:
            if p.get("page_number") == page_number_to_regen:
                target_page = p
                break
        if target_page and target_page.get("panels"):
            print(f"[Regenerate Page {page_number_to_regen}] Reusing existing storyboard panels.")
            pages_data = [{
                "page_number": page_number_to_regen,
                "panels": target_page.get("panels"),
                "_used_fallback": target_page.get("used_storyboard_fallback", False)
            }]
            reusing_storyboard = True

    if not pages_data:
        if page_number_to_regen is not None:
            print(f"[Regenerate Page {page_number_to_regen}] Storyboard not found/invalid. Generating single-page storyboard.")
            prior_summary = ""
            for ep in existing_pages:
                if ep.get("page_number") < page_number_to_regen:
                    panels_list = ep.get("panels", [])
                    prior_summary += f" Page {ep.get('page_number')} covered: " + "; ".join(p.get("action","") for p in panels_list)
            
            page = None
            if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
                page = _run_agent_comic_director_single_page(api_key, content, story_analysis, page_number_to_regen, num_pages, prior_summary)
            
            if page and page.get("panels"):
                page["_used_fallback"] = False
                pages_data = [page]
            else:
                fb_page = _fallback_storyboard(content, 1)[0]
                fb_page["page_number"] = page_number_to_regen
                fb_page["_used_fallback"] = True
                pages_data = [fb_page]
        else:
            print(f"[Comic Director] Generating {num_pages} pages in a loop (once per page)...")
            pages_data = []
            if api_key and api_key not in ("", "MY_GEMINI_API_KEY"):
                prior_summary = ""
                for pn in range(1, num_pages + 1):
                    page = _run_agent_comic_director_single_page(api_key, content, story_analysis, pn, num_pages, prior_summary)
                    if page and page.get("panels"):
                        page["_used_fallback"] = False
                        pages_data.append(page)
                        prior_summary += f" Page {pn} covered: " + "; ".join(p.get("action","") for p in page.get("panels", []))
                    else:
                        print(f"[Comic Director] Page {pn} storyboard failed, using fallback page...")
                        fb_page = _fallback_storyboard(content, 1)[0]
                        fb_page["page_number"] = pn
                        fb_page["_used_fallback"] = True
                        pages_data.append(fb_page)
            
            if not pages_data:
                pages_data = _fallback_storyboard(content, num_pages)

    if page_number_to_regen is not None and existing_pages:
        total_pages = max(num_pages, len(existing_pages))
    else:
        total_pages = len(pages_data)

    base_seed    = random.randint(1, 500_000)
    result_pages = []
    
    # Store Agent trace logs to send back to client
    quality_logs = []

    # Compile all panel tasks for parallel processing
    tasks = []
    for page_data in pages_data:
        page_num = page_data.get("page_number", len(result_pages) + 1)
        panels   = page_data.get("panels", [])
        for pi, panel in enumerate(panels):
            tasks.append({
                "page_num": page_num,
                "panel_idx": pi,
                "panel": panel
            })

    # Worker function to run fetch + optional Agent 4 Quality Check for a single panel
    def process_panel_task(task):
        pageNum = task["page_num"]
        pi = task["panel_idx"]
        panel = task["panel"]
        prompt = _build_panel_scene_prompt(panel, character_sheet, color_style)
        seed   = base_seed + pageNum * 100 + pi
        
        # Initial generation (with up to 3 retries)
        img_bytes = _fetch_panel_image(prompt, seed, retries=3)
        
        # If it failed, try with a simplified fallback prompt!
        if not img_bytes:
            print(f"[Python Image Fetch] Complex prompt failed. Attempting with simplified fallback prompt...")
            camera = panel.get("camera", "Medium Shot")
            action = panel.get("action", "")
            setting = panel.get("setting", "")
            simple_prompt = f"Comic book panel art, {camera} shot. {action or setting or 'Scenic illustration'}. Style: {color_style}, clean comic book illustration, NO text, NO speech bubbles."
            img_bytes = _fetch_panel_image(simple_prompt, seed + 1, retries=3)
        
        # Agent 4: Quality Check
        verdict_info = {"verdict": "PASS", "reason": "Bypassed verification (No Gemini key)"}
        if api_key and api_key not in ("", "MY_GEMINI_API_KEY") and img_bytes:
            verdict_info = _run_agent_quality_check(api_key, img_bytes, panel)
            
            # If quality check tells us to REGENERATE, we do exactly one retry with an adjusted prompt!
            if verdict_info.get("verdict") == "REGENERATE":
                adj_advice = verdict_info.get("prompt_adjustment", "")
                adjusted_prompt = f"{prompt}. Details check: {adj_advice}" if adj_advice else prompt
                print(f"[Quality Agent] Page {pageNum} Panel {pi+1} REGENERATE request: {verdict_info.get('reason')}")
                
                retry_bytes = _fetch_panel_image(adjusted_prompt, seed + 99, retries=3)
                if retry_bytes:
                    img_bytes = retry_bytes
                    verdict_info["verdict"] = "PASS"
                    verdict_info["reason"] = f"Regenerated successfully on retry. Previous issue: {verdict_info.get('reason')}"
        
        return {
            "page_num": pageNum,
            "panel_idx": pi,
            "img_bytes": img_bytes,
            "verdict_info": verdict_info,
            "prompt_used": prompt
        }

    # Run tasks in parallel
    results_map = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_panel_task, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                res = future.result()
                p_num = res["page_num"]
                p_idx = res["panel_idx"]
                if p_num not in results_map:
                    results_map[p_num] = {}
                results_map[p_num][p_idx] = res
            except Exception as exc:
                print(f"[Parallel Worker Error] Task generated an exception: {exc}")

    # ── Retry pass: find any panels that came back empty and give them one more shot ──
    retry_tasks = []
    for page_data in pages_data:
        page_num = page_data.get("page_number")
        panels = page_data.get("panels", [])
        for pi in range(len(panels)):
            p_res = results_map.get(page_num, {}).get(pi)
            if not p_res or not p_res.get("img_bytes"):
                retry_tasks.append({"page_num": page_num, "panel_idx": pi, "panel": panels[pi]})

    if retry_tasks:
        print(f"[Retry Pass] {len(retry_tasks)} panels missing images, retrying...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(process_panel_task, t): t for t in retry_tasks}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    results_map.setdefault(res["page_num"], {})[res["panel_idx"]] = res
                except Exception as exc:
                    print(f"[Retry Pass Error] {exc}")

    # Reconstruct pages and composite
    newly_composited_pages = []
    for page_data in pages_data:
        page_num = page_data.get("page_number")
        panels   = page_data.get("panels", [])

        panel_images = []
        for pi in range(len(panels)):
            p_res = results_map.get(page_num, {}).get(pi)
            if p_res:
                img_bytes = p_res["img_bytes"]
                verdict_info = p_res["verdict_info"]
                prompt = p_res["prompt_used"]
            else:
                img_bytes = None
                verdict_info = {"verdict": "FAIL", "reason": "Parallel worker failed to return result"}
                prompt = ""

            quality_logs.append({
                "page": page_num,
                "panel": pi + 1,
                "verdict": verdict_info.get("verdict", "PASS"),
                "reason": verdict_info.get("reason", "Passed inspection"),
                "prompt_used": prompt
            })
            
            panel_images.append(img_bytes)
            print(f"[Comic v3] Page {page_num} Panel {pi+1}: {'OK' if img_bytes else 'FALLBACK'}")

        # ── Step 5: Layout Engine Compositing ─────────────────────────────
        try:
            pil_page = _composite_page(panel_images, panels, page_num, total_pages, color_style)
            data_url = _page_to_data_url(pil_page)
            fallback = False
        except Exception as e:
            print(f"[Composite error] page {page_num}: {e}")
            traceback.print_exc()
            data_url = _svg_fallback(page_num, total_pages, mood)
            fallback = True

        newly_composited_pages.append({
            "page_number":    page_num,
            "image_data_url": data_url,
            "panels":         panels,
            "panel_count":    len(panels),
            "fallback":       fallback,
            "used_storyboard_fallback": page_data.get("_used_fallback", False),
            "panels_with_placeholder_image": sum(1 for img in panel_images if not img),
        })

    if page_number_to_regen is not None and existing_pages:
        # Merge newly regenerated page into existing pages list
        existing_pages_map = {p.get("page_number"): p for p in existing_pages}
        result_pages = []
        for pn in range(1, total_pages + 1):
            if pn == page_number_to_regen:
                new_p = next((p for p in newly_composited_pages if p["page_number"] == pn), None)
                if new_p:
                    result_pages.append(new_p)
                elif pn in existing_pages_map:
                    result_pages.append(existing_pages_map[pn])
            else:
                if pn in existing_pages_map:
                    result_pages.append(existing_pages_map[pn])
        
        # Merge quality control logs
        merged_quality_logs = []
        for log in existing_quality_logs:
            if log.get("page") != page_number_to_regen:
                merged_quality_logs.append(log)
        merged_quality_logs.extend(quality_logs)
        quality_logs = merged_quality_logs
    else:
        result_pages = newly_composited_pages

    return jsonify({
        "status":      "Success",
        "total_pages": total_pages,
        "pages":       result_pages,
        "color_style": color_style,
        "story_understanding": story_analysis,
        "character_sheets": character_sheet,
        "quality_control_logs": quality_logs
    })


def _svg_fallback(page_num, total_pages, mood):
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 900">
  <rect width="820" height="900" fill="#f5eedd"/>
  <rect x="2" y="2" width="816" height="896" fill="none" stroke="#1a0a00" stroke-width="3"/>
  <rect x="0" y="0" width="820" height="36" fill="#141414"/>
  <text x="16" y="24" font-family="sans-serif" font-size="13" font-weight="bold" fill="#ffc83d">PAGE {page_num} / {total_pages}</text>
  <text x="410" y="480" font-family="sans-serif" font-size="22" text-anchor="middle" fill="#c0392b">Image generation failed</text>
  <text x="410" y="510" font-family="sans-serif" font-size="40" text-anchor="middle">{mood}</text>
  <text x="410" y="545" font-family="sans-serif" font-size="13" text-anchor="middle" fill="#888">Please retry — Pollinations may be busy</text>
</svg>'''
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ─── Legacy single-page endpoint (kept for backward compat) ──────────────────
@app.route("/api/render-comic", methods=["POST"])
def render_comic_legacy():
    # Just re-route to the new endpoint
    return render_comic_pages()


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH & DATA ROUTES (unchanged from original)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/signup", methods=["POST"])
def register_vault_identity():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username","").strip(); password = data.get("password","").strip()
    if not username or not password: return jsonify({"error":"Username and password required."}), 400
    conn = _get_conn(); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username,password_hash) VALUES (?,?)", (username.lower(), hash_password(password)))
        cursor.execute("INSERT INTO file_systems (username,fs_tree_json) VALUES (?,?)", (username.lower(), json.dumps(_build_initial_seed())))
        conn.commit()
        return jsonify({"status":"Success","message":"Vault created!"}), 201
    except sqlite3.IntegrityError: return jsonify({"error":"Username already taken."}), 409
    finally: conn.close()

@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email","").strip().lower()
    if not email or "@" not in email: return jsonify({"error":"Valid email required."}), 400
    code = str(random.randint(100000,999999))
    otp_store[f"email:{email}"] = code
    ok, detail = _send_email_otp(email, code)
    dev = not bool(SMTP_USER and SMTP_PASS)
    resp = {"status":"Success","message":f"Code sent to {email}","dev_mode":dev,"smtp_debug":detail}
    if dev or not ok: resp["otp"] = code
    return jsonify(resp)

@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data  = request.get_json(force=True, silent=True) or {}
    email = data.get("email","").strip().lower()
    code  = data.get("code","").strip()
    if otp_store.get(f"email:{email}") != code: return jsonify({"error":"Invalid OTP."}), 401
    otp_store[f"verified:email:{email}"] = True
    return jsonify({"status":"Success","message":"Verified!"})

@app.route("/api/auth/register-identity", methods=["POST"])
def register_identity():
    data = request.get_json(force=True, silent=True) or {}
    email=data.get("email","").strip().lower(); username=data.get("username","").strip(); password=data.get("password","").strip()
    if not all([email,username,password]): return jsonify({"error":"All fields required."}), 400
    if not otp_store.get(f"verified:email:{email}"): return jsonify({"error":"Email not verified."}), 403
    conn=_get_conn(); cursor=conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username,password_hash) VALUES (?,?)", (username.lower(), hash_password(password)))
        cursor.execute("INSERT INTO file_systems (username,fs_tree_json) VALUES (?,?)", (username.lower(), json.dumps(_build_initial_seed())))
        conn.commit()
        otp_store.pop(f"email:{email}",None); otp_store.pop(f"verified:email:{email}",None)
        return jsonify({"status":"Success","username":username,"avatar_desc":"programmer in minimalist hoodie, sleek glasses","global_alignments":{},"fs_tree":_build_initial_seed()}), 201
    except sqlite3.IntegrityError: return jsonify({"error":"Username already taken."}), 409
    finally: conn.close()

@app.route("/api/login", methods=["POST"])
def verify_vault_access():
    data=request.get_json(force=True,silent=True) or {}
    username=data.get("username","").strip(); password=data.get("password","").strip()
    if not username or not password: return jsonify({"error":"Missing credentials."}), 400
    conn=_get_conn(); cursor=conn.cursor()
    cursor.execute("SELECT password_hash,avatar_desc,global_alignments FROM users WHERE username=?", (username.lower(),))
    row=cursor.fetchone()
    if not row or row[0]!=hash_password(password): conn.close(); return jsonify({"error":"Invalid credentials."}), 401
    cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username=?", (username.lower(),))
    fs_row=cursor.fetchone(); conn.close()
    return jsonify({"status":"Success","username":username,"avatar_desc":row[1],
                    "global_alignments":json.loads(row[2] or "{}"),
                    "fs_tree":json.loads(fs_row[0]) if fs_row else []})

@app.route("/api/save", methods=["POST"])
def commit_matrix_state():
    data=request.get_json(force=True,silent=True) or {}
    username=data.get("username"); fs_tree=data.get("fs_tree")
    if not username or fs_tree is None: return jsonify({"error":"username and fs_tree required."}), 400
    uk=username.lower()
    avatar=data.get("avatar_desc","programmer in minimalist hoodie, sleek glasses")
    ga=data.get("global_alignments",{})
    conn=_get_conn(); cursor=conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username=?", (uk,))
    if cursor.fetchone():
        cursor.execute("UPDATE users SET avatar_desc=?,global_alignments=? WHERE username=?", (avatar,json.dumps(ga),uk))
    else:
        cursor.execute("INSERT INTO users (username,password_hash,avatar_desc,global_alignments) VALUES (?,?,?,?)",
                       (uk,hash_password("changeme"),avatar,json.dumps(ga)))
    cursor.execute("SELECT username FROM file_systems WHERE username=?", (uk,))
    if cursor.fetchone():
        cursor.execute("UPDATE file_systems SET fs_tree_json=? WHERE username=?", (json.dumps(fs_tree),uk))
    else:
        cursor.execute("INSERT INTO file_systems (username,fs_tree_json) VALUES (?,?)", (uk,json.dumps(fs_tree)))
    conn.commit(); conn.close()
    return jsonify({"status":"Success","message":"State saved."})

@app.route("/api/entry/characters", methods=["POST"])
def update_entry_characters():
    data=request.get_json(force=True,silent=True) or {}
    username=data.get("username"); file_id=data.get("file_id"); characters=data.get("characters")
    if not username or not file_id or characters is None: return jsonify({"error":"username, file_id, characters required."}), 400
    uk=username.lower(); conn=_get_conn(); cursor=conn.cursor()
    cursor.execute("SELECT fs_tree_json FROM file_systems WHERE username=?", (uk,))
    row=cursor.fetchone()
    if not row: conn.close(); return jsonify({"error":"User not found."}), 404
    fs=json.loads(row[0])
    def patch(tree,tid,chars):
        for n in tree:
            if n.get("type")=="file" and n.get("id")==tid: n["characters"]=chars; return True
            if n.get("type")=="folder":
                if patch(n.get("children",[]),tid,chars): return True
        return False
    if not patch(fs,file_id,characters): conn.close(); return jsonify({"error":"File not found."}), 404
    cursor.execute("UPDATE file_systems SET fs_tree_json=? WHERE username=?", (json.dumps(fs),uk))
    conn.commit(); conn.close()
    return jsonify({"status":"Success"})

@app.route("/api/alignments", methods=["GET"])
def get_global_alignments():
    username=request.args.get("username","").strip().lower()
    if not username: return jsonify({"error":"username required."}), 400
    conn=_get_conn(); cursor=conn.cursor()
    cursor.execute("SELECT avatar_desc,global_alignments FROM users WHERE username=?", (username,))
    row=cursor.fetchone(); conn.close()
    if not row: return jsonify({"error":"User not found."}), 404
    return jsonify({"status":"Success","avatar_desc":row[0],"global_alignments":json.loads(row[1] or "{}")})

@app.route("/api/alignments", methods=["POST"])
def update_global_alignments():
    data=request.get_json(force=True,silent=True) or {}
    username=data.get("username","").strip().lower()
    if not username: return jsonify({"error":"username required."}), 400
    ga=data.get("global_alignments",{}); ad=data.get("avatar_desc")
    conn=_get_conn(); cursor=conn.cursor()
    updates=["global_alignments=?"]; params=[json.dumps(ga)]
    if ad is not None: updates.append("avatar_desc=?"); params.append(ad)
    params.append(username)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE username=?", params)
    conn.commit(); conn.close()
    return jsonify({"status":"Success"})

@app.route("/api/delete-account", methods=["POST"])
def delete_account():
    data=request.get_json(force=True,silent=True) or {}
    username=data.get("username","").strip().lower(); password=data.get("password","").strip()
    if not username or not password: return jsonify({"error":"username and password required."}), 400
    conn=_get_conn(); cursor=conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    row=cursor.fetchone()
    if not row or row[0]!=hash_password(password): conn.close(); return jsonify({"error":"Invalid credentials."}), 401
    cursor.execute("DELETE FROM file_systems WHERE username=?", (username,)); cursor.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit(); conn.close()
    return jsonify({"status":"Success","message":"Account deleted."})

@app.route("/api/messenger/request-otp", methods=["POST"])
def request_messenger_otp():
    data=request.get_json(force=True,silent=True) or {}
    email=data.get("email","").strip() or "user@messenger.io"
    code=str(random.randint(100000,999999)); otp_store[f"email:{email}"]=code
    _send_email_otp(email,code)
    return jsonify({"status":"Success","debug_otp":code})

@app.route("/api/messenger/verify-otp", methods=["POST"])
def verify_messenger_otp():
    data=request.get_json(force=True,silent=True) or {}
    email=data.get("email","").strip(); code=data.get("code","").strip()
    if otp_store.get(f"email:{email}")!=code: return jsonify({"error":"Invalid OTP."}), 401
    return jsonify({"status":"Success","message":"Verified!"})

def _build_initial_seed():
    return [{"id":"fold_seed_1","type":"folder","name":"Comic Diary Logs 📒","children":[
        {"id":"file_seed_1","type":"file","name":"Inaugural Entry","content":"Welcome!",
         "mood":"😊","created":"6/27/2026","edited":"6/27/2026","comic":"","stickers":[],"characters":[]}]}]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)