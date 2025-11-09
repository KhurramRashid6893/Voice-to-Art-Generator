import os
import json
import time
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory
from google import genai  # Gemini SDK

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/gallery"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ===============================================
# CONFIGURATION
# ===============================================
CONFIG = {
    "stability": {
        "endpoint": "https://api.stability.ai/v2beta/stable-image/generate/core",
        "keys": [
            "sk-xY925Lvv8GQLcqBPfrHIpJLHFCsm2bFUoTZ2zUb1OEYZutV1",
            "sk-Rt03FGD4wiNOF0praLJM3LF6tBBqeKVIGVcQNdlWiWLLzAr3",
            "sk-YwffXJUFPt7ZUc93FTGLUmrMVEsjdVmFETIcmXXvwENmAns1",
            "sk-x0RMjdzYEP50Qf2BWosuuYHMo8X1T5QxbdVLRPrcShaddKJ5"
        ]
    },
    "pollinations": {
        "endpoint": "https://image.pollinations.ai/prompt/"
    },
    "gemini": {
        "keys": [
            "AIzaSyBZ_Mea6_FaJVcWTYhc4r1OAlGzjdQIkxw",
            "AIzaSyCyuyG-IxIyJYp4sw5BpJCPWUlUvG-M9lw",
            "AIzaSyA9rvL4I_VTJ6SPGZ19Ug-xbXfUxT5GZrU",
            "AIzaSyDZS2J4I02v_fogb47qbpFzUOiZFpt8-CI",
            "AIzaSyAfX5U8uu5fLpqTNEn9pvibUWh9PWLAFrk",
            "AIzaSyDdFU9MHjKf6Ga-cXzvE-niOnGACx8BQI4"
        ]
    },
    "status_file": "api_status.json",
    "timeout": 40
}

# ===============================================
# STATUS MANAGEMENT (for key rotation)
# ===============================================
def load_status():
    """Load or initialize API key rotation status with auto-repair."""
    if os.path.exists(CONFIG["status_file"]):
        try:
            with open(CONFIG["status_file"], "r") as f:
                status = json.load(f)
            # 🔧 Auto-fix mismatched key counts
            for service in ["stability", "gemini"]:
                n_keys = len(CONFIG[service]["keys"])
                if service not in status:
                    status[service] = {"index": 0, "failed": [False] * n_keys, "last_fail": [0] * n_keys}
                else:
                    # Resize lists safely
                    for keyname in ["failed", "last_fail"]:
                        while len(status[service][keyname]) < n_keys:
                            status[service][keyname].append(False if keyname == "failed" else 0)
                        while len(status[service][keyname]) > n_keys:
                            status[service][keyname].pop()
            save_status(status)
            return status
        except Exception as e:
            print(f"⚠️ Corrupted status file, resetting. ({e})")

    # Create fresh structure
    status = {
        "stability": {
            "index": 0,
            "failed": [False] * len(CONFIG["stability"]["keys"]),
            "last_fail": [0] * len(CONFIG["stability"]["keys"])
        },
        "gemini": {
            "index": 0,
            "failed": [False] * len(CONFIG["gemini"]["keys"]),
            "last_fail": [0] * len(CONFIG["gemini"]["keys"])
        }
    }
    save_status(status)
    return status

def save_status(status):
    with open(CONFIG["status_file"], "w") as f:
        json.dump(status, f)

status = load_status()

def get_next_key(service):
    """Rotate keys for Stability or Gemini."""
    keys = CONFIG[service]["keys"]
    s = status[service]
    n = len(keys)
    for i in range(n):
        idx = (s["index"] + i) % n
        if not s["failed"][idx]:
            s["index"] = (idx + 1) % n
            save_status(status)
            return keys[idx], idx
    # reset after 1 hour cooldown
    now = time.time()
    for i, t in enumerate(s["last_fail"]):
        if now - t > 3600:
            s["failed"][i] = False
            s["last_fail"][i] = 0
    save_status(status)
    return keys[0], 0

def mark_key_failed(service, idx):
    s = status[service]
    s["failed"][idx] = True
    s["last_fail"][idx] = time.time()
    save_status(status)

# ===============================================
# GEMINI PROMPT EXPANSION
# ===============================================
def expand_prompt_with_gemini(user_prompt: str, mode: str = "normal") -> str:
    """
    Expand user's input using rotating Gemini API keys.
    Now includes emotional tone analysis to adjust color, lighting, and mood dynamically.
    """
    for _ in range(len(CONFIG["gemini"]["keys"])):
        key, idx = get_next_key("gemini")
        try:
            client = genai.Client(api_key=key)

            # 💬 Emotion Detection Layer
            emotion_analysis_prompt = (
                "Analyze the user's message and describe their emotional tone "
                "(e.g., calm, energetic, proud, excited, thoughtful, confident, sad, joyful, etc.). "
                "Respond with one emotion word only."
            )
            emotion_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[emotion_analysis_prompt, user_prompt]
            )
            emotion = ""
            for part in emotion_response.parts:
                if hasattr(part, "text"):
                    emotion += part.text.strip().lower()
            if not emotion:
                emotion = "neutral"
            print(f"🧠 Detected emotion: {emotion}")

            # 🎨 Prompt Generation Layer
            if mode == "pattern":
                system_prompt = (
                    f"You are an AI artist specialized in abstract generative art. "
                    f"Create an art prompt that represents the energy, motion, and sound of the user's words "
                    f"as flowing light, particles, or wave patterns. The emotional tone is '{emotion}'. "
                    f"Use colors, brightness, and rhythm to reflect that mood — "
                    f"for example, calm → soft blues, excited → glowing reds/oranges, proud → gold, confident → violet, sad → dark indigo. "
                    f"Focus on motion, symmetry, and vibrancy. Output only the final descriptive prompt."
                )
            else:
                system_prompt = (
                    f"You are an expert AI art prompt engineer. "
                    f"Expand the user's words into a rich, descriptive, cinematic prompt suitable for realistic or digital artwork. "
                    f"The emotional tone is '{emotion}', so match it in lighting, atmosphere, and color palette. "
                    f"For example, calm → pastel tones and smooth gradients; energetic → dynamic poses and neon light; "
                    f"proud → golden glow and centered composition. Output only the improved prompt."
                )

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[system_prompt, user_prompt]
            )

            text = ""
            for part in response.parts:
                if hasattr(part, "text"):
                    text += part.text
            if text.strip():
                return text.strip()
        except Exception as e:
            print(f"⚠️ Gemini key {idx} failed: {e}")
            mark_key_failed("gemini", idx)
            continue

    print("⚠️ All Gemini keys failed.")
    return user_prompt


# ===============================================
# IMAGE GENERATION
# ===============================================
def detect_limit_error(resp):
    if not resp:
        return False
    if resp.status_code in (401, 402, 403, 429, 503):
        return True
    try:
        j = resp.json()
        msg = json.dumps(j).lower()
        if any(k in msg for k in ["quota", "limit", "exceed", "insufficient", "rate"]):
            return True
    except Exception:
        pass
    return False

def generate_with_stability(prompt):
    for _ in range(len(CONFIG["stability"]["keys"])):
        key, idx = get_next_key("stability")
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "image/png"
        }
        data = {"prompt": prompt}
        try:
            r = requests.post(CONFIG["stability"]["endpoint"], headers=headers, data=data, timeout=CONFIG["timeout"])
            if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
                return r.content
            if detect_limit_error(r):
                mark_key_failed("stability", idx)
                continue
        except Exception:
            mark_key_failed("stability", idx)
            continue
    return None

def generate_with_pollinations(prompt):
    try:
        url = CONFIG["pollinations"]["endpoint"] + requests.utils.quote(prompt)
        r = requests.get(url, timeout=CONFIG["timeout"])
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


### Pillow fallback generator
from PIL import Image, ImageDraw, ImageFilter
import random
def generate_with_pillow(prompt):
    """
    Local fallback generator that creates an abstract pattern based on the prompt text.
    Uses color words and randomness to make a unique 'AI-style' art piece.
    """
    print("🌀 Using Pillow fallback generator...")

    # Define canvas
    width, height = 768, 512
    img = Image.new("RGB", (width, height), color=(10, 10, 20))
    draw = ImageDraw.Draw(img)

    # Pick base color themes depending on prompt mood keywords
    colors = {
        "warm": [(255, 180, 90), (255, 100, 60), (200, 50, 40)],
        "cool": [(60, 100, 255), (30, 60, 120), (80, 160, 220)],
        "neutral": [(120, 120, 130), (180, 180, 190), (60, 60, 70)],
        "vibrant": [(255, 60, 120), (255, 180, 30), (120, 220, 255)],
    }

    text_lower = prompt.lower()
    if any(k in text_lower for k in ["red", "gold", "orange", "fire", "warm"]):
        palette = colors["warm"]
    elif any(k in text_lower for k in ["blue", "violet", "indigo", "cool"]):
        palette = colors["cool"]
    elif any(k in text_lower for k in ["gray", "tired", "neutral", "calm"]):
        palette = colors["neutral"]
    else:
        palette = colors["vibrant"]

    # Draw abstract pattern (random circles and waves)
    for _ in range(random.randint(80, 150)):
        x0 = random.randint(-100, width)
        y0 = random.randint(-100, height)
        size = random.randint(30, 200)
        color = random.choice(palette)
        draw.ellipse([x0, y0, x0 + size, y0 + size], fill=color, outline=None)

    # Add gradient blur effect
    img = img.filter(ImageFilter.GaussianBlur(radius=random.randint(6, 12)))

    # Add wave lines
    for _ in range(10):
        y = random.randint(0, height)
        for x in range(width):
            c = random.choice(palette)
            draw.point((x, y + random.randint(-2, 2)), fill=c)

    print("🎨 Pillow fallback art generated successfully.")
    return img



def generate_image(prompt):
    print(f"🧩 Generating image for prompt: {prompt[:120]}...")

    # Try Stability
    img_bytes = generate_with_stability(prompt)
    if img_bytes:
        print("✅ Stability image generated successfully.")
        return img_bytes, "stability"

    print("⚠️ Stability failed. Trying Pollinations...")
    img_bytes = generate_with_pollinations(prompt)
    if img_bytes:
        print("✅ Pollinations image generated successfully.")
        return img_bytes, "pollinations"

    print("❌ All APIs failed. Using local Pillow fallback...")
    # Local fallback
    img = generate_with_pillow(prompt)
    from io import BytesIO
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue(), "pillow"


# ===============================================
# ROUTES
# ===============================================
@app.route('/')
def index():
    images = sorted(os.listdir(app.config["UPLOAD_FOLDER"]))
    images = [f"gallery/{img}" for img in images]
    return render_template('index.html', images=images)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_prompt = data.get("prompt", "").strip()
    mode = data.get("mode", "normal")

    if not user_prompt:
        return jsonify({"error": "Prompt required."}), 400

    # Step 1: expand prompt using Gemini (rotating keys)
    expanded_prompt = expand_prompt_with_gemini(user_prompt, mode)
    print(f"🧠 Detected emotion (if any): extracted inside Gemini")  # if you’re adding emotion logic
    print(f"🎨 Mode: {mode} | 🪄 Gemini expanded: {expanded_prompt}")

    # Step 2: generate art using Stability/Pollinations
    try:
        img, provider = generate_image(expanded_prompt)
        
        if not img:
            print("⚠️ No image returned from Stability or Pollinations.")
            return jsonify({"error": "No image returned. Possibly API limit reached."}), 500

        # --- *** NEW CROPPING LOGIC *** ---
        if provider == "pollinations":
            try:
                from io import BytesIO
                from PIL import Image
                
                print("🌀 Pollinations image detected. Cropping watermark...")
                pil_image = Image.open(BytesIO(img))
                width, height = pil_image.size
                
                # Crop 40px from the bottom
                crop_amount = 50 
                if height > crop_amount:
                    box = (0, 0, width, height - crop_amount)
                    cropped_image = pil_image.crop(box)
                    
                    # Save cropped image back to bytes
                    buffer = BytesIO()
                    cropped_image.save(buffer, format="PNG")
                    img = buffer.getvalue() # Overwrite 'img' with cropped bytes
                    print("✅ Image cropped successfully.")
                else:
                    print("⚠️ Image is too short to crop, skipping.")
            except Exception as e:
                print(f"💥 Failed to crop image: {e}")
                # Don't fail the request, just use the uncropped image
        # --- *** END OF NEW LOGIC *** ---

        filename = f"art_{len(os.listdir(app.config['UPLOAD_FOLDER'])) + 1}.png"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        with open(path, "wb") as f:
            f.write(img)

        print(f"✅ Image saved successfully: {filename} via {provider}")

        return jsonify({
            "message": "✅ Art generated successfully!",
            "mode": mode,
            "original_prompt": user_prompt,
            "expanded_prompt": expanded_prompt,
            "image": f"gallery/{filename}",
            "provider": provider
        })
    except Exception as e:
        print(f"💥 Exception in image generation: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/static/gallery/<path:filename>')
def gallery(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)