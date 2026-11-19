#!/usr/bin/env python3
"""
ComfyUI Bridge Server for Sketch-to-Art Kiosk
Connects the web kiosk to ComfyUI at http://10.7.5.109:8188
Serves the web kiosk on GET, handles generation on POST /generate
"""

import os
import sys
import json
import uuid
import time
import email
import socket
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PIL import Image, ImageDraw, ImageFont, ImageOps

COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "http://10.7.5.109:8190")
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
WORKFLOW_API_PATH = os.path.join(BASE_DIR, "workflow_api.json")

def upload_image_to_comfy(image_bytes, filename="drawing.png"):
    boundary = uuid.uuid4().hex
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode())
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(image_bytes)
    body.extend(b"\r\n")
    
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
    body.extend(b"true\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    
    req = urllib.request.Request(f"{COMFYUI_HOST}/upload/image", data=body, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def queue_prompt(prompt_workflow, client_id):
    payload = json.dumps({"prompt": prompt_workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_HOST}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[-] ComfyUI /prompt rejected with HTTP {e.code}:\n{err_body}")
        try:
            err_json = json.loads(err_body)
            node_errors = err_json.get("node_errors", {})
            for nid, err in node_errors.items():
                print(f"[-] Node {nid} error: {err}")
        except Exception:
            pass
        raise RuntimeError(f"ComfyUI Error ({e.code}): {err_body}")

def poll_history(prompt_id, timeout=180):
    start = time.time()
    last_print = 0
    while time.time() - start < timeout:
        time.sleep(1.0)
        elapsed = int(time.time() - start)
        if elapsed - last_print >= 5:
            last_print = elapsed
            print(f"[+] GPU processing... {elapsed}s elapsed")
        req = urllib.request.Request(f"{COMFYUI_HOST}/history/{prompt_id}")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                if prompt_id in data:
                    return data[prompt_id]
        except Exception:
            pass
    raise TimeoutError(f"Generation timed out after {timeout}s")

def extract_output_url(history_data):
    outputs = history_data.get("outputs", {})
    for node_id, out in outputs.items():
        for key in ("videos", "gifs"):
            if key in out and out[key]:
                v = out[key][0]
                params = urllib.parse.urlencode({
                    "filename": v["filename"],
                    "subfolder": v.get("subfolder", ""),
                    "type": v.get("type", "output")
                })
                return f"{COMFYUI_HOST}/view?{params}", True
        if "images" in out and out["images"]:
            img = out["images"][0]
            fname = img["filename"]
            params = urllib.parse.urlencode({
                "filename": fname,
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")
            })
            is_vid = any(fname.lower().endswith(ext) for ext in (".mp4", ".webm", ".mov", ".mkv", ".gif"))
            return f"{COMFYUI_HOST}/view?{params}", is_vid
    return None, False

def build_prompt_for_style(style):
    style_directives = {
        "3d-cartoon": (
            "3D CARTOON & PIXAR ANIMATION AESTHETIC.\n"
            "The drawing inflates into a smooth, glossy 3D clay figurine with vibrant cheerful colors, "
            "soft studio bounce lighting, rounded volumetric depth, and playful toy-like finish."
        ),
        "watercolor": (
            "VIBRANT WATERCOLOR PAINTING AESTHETIC.\n"
            "The drawing blooms into rich, flowing watercolor washes (cerulean, magenta, amber, turquoise) "
            "with organic wet-on-wet paint pooling, fine paper granulation, and luminous translucent gradients."
        ),
        "storybook": (
            "HAND-PAINTED STORYBOOK ILLUSTRATION AESTHETIC.\n"
            "The drawing transforms into a warm, cozy fairy-tale book illustration painted with gouache and soft pastels, "
            "with charming storybook textures, gentle lighting, and artisanal hand-drawn charm."
        ),
        "anime": (
            "VIBRANT ANIME ANIMATION AESTHETIC.\n"
            "The drawing transforms into crisp modern Japanese anime art with vivid cel-shaded color fills, "
            "smooth gradient highlights, clean sharp contours, and high-energy animation styling."
        ),
        "realistic": (
            "PHOTOREALISTIC 3D PHYSICAL SCULPTURE AESTHETIC.\n"
            "The drawing rises into a tangible solid 3D sculpture crafted from smooth glazed ceramic and brushed metal, "
            "with authentic physical depth, subtle bevels, and realistic contact drop-shadows."
        )
    }
    desc = style_directives.get(style, style_directives["realistic"])
    return f"""{desc}

CORE RULE: EXACT SHAPE PRESERVATION & ZERO HALLUCINATIONS.
The uploaded image is the sole geometric blueprint. Transform ONLY the exact drawn silhouette into the styled form. Do not invent any extra parts, secondary shapes, decorative clutter, or background elements. The surrounding background must remain completely pristine, pure white paper with soft natural contact shadows directly beneath the object.

5-SECOND PROGRESSION:
0–1 s: the source drawing resting cleanly on the white page.
1–3 s: the drawing rises upward, acquiring clean 3D volume, rich surface colors, and smooth sculptural depth strictly within its original boundary.
3–4.5 s: authentic materials, soft highlights, and realistic contact drop-shadows settle smoothly onto the solid form.
4.5–5 s: subtle resting posture breathing motion only, remaining perfectly anchored in place.

LOOK AND COMPOSITION:
Fixed camera angle. Pristine studio product lighting, vertical 9:16 portrait. High clarity, completely clean empty white surroundings, razor-sharp isolated subject."""

def render_frame_overlay(sketch_path, creator_name, out_overlay_path):
    FW, FH = 768, 1024
    VX, VY, VW, VH = 68, 98, 632, 816

    overlay = Image.new("RGBA", (FW, FH), (0, 15, 162, 255))
    draw = ImageDraw.Draw(overlay)

    # 1. BMU SAAR Logo at top
    logo_candidates = [
        os.path.join(BASE_DIR, "bmu_saar_logo_web.png"),
        os.path.join(BASE_DIR, "BMU_SAAR Logo-White.png")
    ]
    for lp in logo_candidates:
        if os.path.exists(lp):
            try:
                logo = Image.open(lp).convert("RGBA")
                lw = 400
                lh = int(logo.height * (lw / logo.width))
                logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
                lx = (FW - lw) // 2
                overlay.paste(logo, (lx, 22), logo)
                break
            except Exception as e:
                print(f"[-] Could not load logo {lp}: {e}")

    # 2. Cutout window for video (set alpha to 0 so video displays cleanly underneath)
    for y in range(VY, VY + VH):
        for x in range(VX, VX + VW):
            overlay.putpixel((x, y), (0, 0, 0, 0))

    # 3. Sketch Picture-in-Picture badge in bottom-left corner of the video window
    if sketch_path and os.path.exists(sketch_path):
        try:
            sk = Image.open(sketch_path).convert("RGBA")
            bw, bh = 130, 130
            bx, by = VX + 16, VY + VH - bh - 16
            card = Image.new("RGBA", (bw, bh), (255, 255, 255, 255))
            cdraw = ImageDraw.Draw(card)
            cdraw.rectangle([(0, 0), (bw - 1, bh - 1)], outline=(226, 232, 240, 255), width=2)
            
            sk.thumbnail((bw - 20, bh - 36), Image.Resampling.LANCZOS)
            card.paste(sk, ((bw - sk.width) // 2, 8), sk)
            
            font_small = None
            for fp in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
            ]:
                if os.path.exists(fp):
                    font_small = ImageFont.truetype(fp, 11)
                    break
            if not font_small:
                font_small = ImageFont.load_default()
            cdraw.text((bw // 2, bh - 14), "Your sketch", fill=(15, 23, 42, 255), font=font_small, anchor="mm")
            overlay.paste(card, (bx, by), card)
        except Exception as e:
            print(f"[-] PIP badge error: {e}")

    # 4. Creator name at bottom
    cname = (creator_name or "BMU CREATOR").strip().upper()
    text = f"CREATED BY: {cname}"
    font_large = None
    for fp in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]:
        if os.path.exists(fp):
            font_large = ImageFont.truetype(fp, 24)
            break
    if not font_large:
        font_large = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(((FW - tw) // 2, 955), text, fill=(255, 255, 255, 255), font=font_large)

    overlay.save(out_overlay_path)
    return out_overlay_path

def generate_framed_media(raw_filepath, is_video, sketch_path, creator_name, out_video_path, out_poster_path):
    overlay_path = os.path.join(OUTPUTS_DIR, f"overlay_temp_{int(time.time()*1000)}.png")
    render_frame_overlay(sketch_path, creator_name, overlay_path)

    try:
        if is_video:
            # Composite video covering 632x816 within 768x1024 royal blue frame (cover fit, no white bars)
            filter_str = (
                "[0:v]scale=632:816:force_original_aspect_ratio=increase,crop=632:816[vid];"
                "color=c=0x000fa2:s=768x1024:d=5[bg];"
                "[bg][vid]overlay=68:98[base];"
                "[base][1:v]overlay=0:0[out]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_filepath,
                "-i", overlay_path,
                "-filter_complex", filter_str,
                "-map", "[out]",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_video_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

            # Generate poster image from frame at 1s
            cmd_poster = [
                "ffmpeg", "-y",
                "-i", out_video_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                out_poster_path
            ]
            subprocess.run(cmd_poster, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        else:
            # Composite single image covering 632x816 without borders
            raw_img = Image.open(raw_filepath).convert("RGBA")
            fitted = ImageOps.fit(raw_img, (632, 816), method=Image.Resampling.LANCZOS)
            base = Image.new("RGBA", (768, 1024), (0, 15, 162, 255))
            base.paste(fitted, (68, 98), fitted)
            
            overlay = Image.open(overlay_path).convert("RGBA")
            base.paste(overlay, (0, 0), overlay)
            base.save(out_poster_path, "PNG")

    finally:
        if os.path.exists(overlay_path):
            try:
                os.remove(overlay_path)
            except Exception:
                pass

def parse_multipart_data(content_type_header, body_bytes):
    msg = email.message_from_bytes(
        b"Content-Type: " + content_type_header.encode() + b"\r\n\r\n" + body_bytes
    )
    fields = {}
    for part in msg.walk():
        if part.is_multipart():
            continue
        cd = part.get("Content-Disposition", "")
        name = None
        for item in cd.split(";"):
            item = item.strip()
            if item.startswith("name="):
                name = item.split("=", 1)[1].strip("\"'")
        if name:
            fields[name] = part.get_payload(decode=True)
    return fields

class KioskHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split("?")[0]
        if clean_path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if clean_path in ("/status", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "status": "online",
                "comfyui_host": COMFYUI_HOST,
                "workflow_api_found": os.path.exists(WORKFLOW_API_PATH)
            }
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))
            return

        if clean_path == "/share":
            parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            gen_id = parsed_qs.get("id", [""])[0]
            download_now = parsed_qs.get("download", ["0"])[0] == "1"

            video_filename = f"framed_{gen_id}.mp4"
            image_filename = f"framed_{gen_id}.png"
            video_rel = f"/outputs/{video_filename}"
            image_rel = f"/outputs/{image_filename}"
            has_video = os.path.exists(os.path.join(OUTPUTS_DIR, video_filename))

            if download_now and has_video:
                self.send_response(302)
                self.send_header("Location", video_rel)
                self.end_headers()
                return

            video_markup = f"<video src='{video_rel}' poster='{image_rel}' autoplay loop muted playsinline controls></video>" if has_video else f"<img src='{image_rel}' alt='AI Artwork'>"
            download_video_btn = f"<a href='{video_rel}' download='BMU_Framed_Artwork_{gen_id}.mp4' class='btn btn-primary'>⬇ Download Framed Video (.mp4)</a>" if has_video else ""

            html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>BMU Founder's Day — Your Framed AI Artwork</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #060814;
      color: #ffffff;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 18px 14px 40px;
    }}
    .header {{
      text-align: center;
      margin-bottom: 16px;
    }}
    .header img {{
      max-width: 290px;
      height: auto;
      margin-bottom: 6px;
    }}
    .subtitle {{
      color: #93c5fd;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}
    .player-wrap {{
      width: 100%;
      max-width: 390px;
      background: #000fa2;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.15);
      margin-bottom: 20px;
    }}
    .player-wrap video, .player-wrap img {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .actions {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      width: 100%;
      max-width: 390px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 15px 20px;
      border-radius: 99px;
      font-size: 16px;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      text-align: center;
      transition: transform .15s, opacity .15s;
    }}
    .btn:active {{ transform: scale(0.97); opacity: 0.9; }}
    .btn-primary {{
      background: linear-gradient(135deg, #ec4899, #8b5cf6 55%, #3b82f6);
      color: #fff;
      box-shadow: 0 8px 24px rgba(139, 92, 246, 0.45);
    }}
    .btn-secondary {{
      background: rgba(255, 255, 255, 0.08);
      color: #e2e8f0;
      border: 1px solid rgba(255, 255, 255, 0.18);
    }}
    .footer-note {{
      margin-top: 24px;
      color: #64748b;
      font-size: 12px;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="header">
    <img src="/bmu_saar_logo_web.png" alt="BML Munjal University / SAAR" onerror="this.style.display='none'">
    <div class="subtitle">Founder's Day · Commemorative Artwork</div>
  </div>

  <div class="player-wrap">
    {video_markup}
  </div>

  <div class="actions">
    {download_video_btn}
    <a href="{image_rel}" download="BMU_Framed_Photo_{gen_id}.png" class="btn btn-secondary">🖼️ Download Framed Photo (.png)</a>
  </div>

  <div class="footer-note">
    BML Munjal University — A Hero Group Initiative<br>
    The Essence of BMU · 2026
  </div>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_page.encode("utf-8"))
            return
        
        # Serve index.html and other static files
        super().do_GET()

    def do_POST(self):
        clean_path = self.path.split("?")[0]
        if clean_path == "/generate":
            try:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type:
                    self.send_error(400, "Expected multipart/form-data")
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(content_length)

                fields = parse_multipart_data(content_type, body_bytes)
                drawing_bytes = fields.get("drawing")
                style_bytes = fields.get("style", b"realistic")
                style = style_bytes.decode() if isinstance(style_bytes, bytes) else str(style_bytes)
                creator_name_raw = fields.get("creator_name", b"BMU CREATOR")
                creator_name = creator_name_raw.decode("utf-8", errors="ignore") if isinstance(creator_name_raw, bytes) else str(creator_name_raw)
                if not creator_name.strip():
                    creator_name = "BMU CREATOR"

                if not drawing_bytes:
                    self.send_error(400, "Missing 'drawing' file")
                    return

                # 1. Upload sketch to ComfyUI
                gen_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
                filename = f"sketch_{gen_id}.png"
                
                # Save a local copy for debugging and re-framing
                local_debug_path = os.path.join(BASE_DIR, "last_drawing.png")
                with open(local_debug_path, "wb") as f_debug:
                    f_debug.write(drawing_bytes)
                sketch_saved_path = os.path.join(OUTPUTS_DIR, f"sketch_{gen_id}.png")
                with open(sketch_saved_path, "wb") as f_sk:
                    f_sk.write(drawing_bytes)

                upload_res = upload_image_to_comfy(drawing_bytes, filename=filename)
                uploaded_name = upload_res.get("name", filename)
                print(f"[+] Uploaded sketch to ComfyUI: {uploaded_name}")
                print(f"[+] View uploaded image directly at: {COMFYUI_HOST}/view?filename={uploaded_name}&type=input")
                print(f"[+] Saved local copy to: {local_debug_path}")

                # 2. Check and load API workflow
                if not os.path.exists(WORKFLOW_API_PATH):
                    raise FileNotFoundError(
                        f"Missing '{WORKFLOW_API_PATH}'. "
                        "Open ComfyUI at http://10.7.5.109:8188 -> Enable Dev Mode -> Click 'Save (API Format)' -> save as workflow_api.json."
                    )

                with open(WORKFLOW_API_PATH, "r", encoding="utf-8") as f:
                    workflow = json.load(f)

                # 3. Inject uploaded image into LoadImage node
                for node_id, node in workflow.items():
                    if node.get("class_type") == "LoadImage":
                        node["inputs"]["image"] = uploaded_name
                        break

                # 4. Inject style-tailored prompt into MiniMaxH3ImageToVideo node
                styled_prompt = build_prompt_for_style(style)
                for node_id, node in workflow.items():
                    if node.get("class_type") == "MiniMaxH3ImageToVideo":
                        node["inputs"]["prompt"] = styled_prompt
                        print(f"[+] Injected style directive for: '{style}'")
                        break

                duration = 5.0
                if "duration" in fields:
                    try:
                        dur_val = float(fields["duration"].decode() if isinstance(fields["duration"], bytes) else fields["duration"])
                        if dur_val > 0:
                            duration = dur_val
                    except Exception:
                        pass

                # Enforce parameters: set duration (default 5.0s), 0.88 denoise; preserve workflow megapixels
                if "7:133" in workflow:
                    workflow["7:133"]["inputs"]["value"] = duration
                if "5" in workflow and "megapixels" not in workflow["5"]["inputs"]:
                    workflow["5"]["inputs"]["megapixels"] = 0.1
                if "7:124" in workflow:
                    workflow["7:124"]["inputs"]["denoise"] = 0.88

                # 5. Queue prompt
                client_id = str(uuid.uuid4())
                print(f"[+] Queuing prompt to ComfyUI ({COMFYUI_HOST})...")
                res = queue_prompt(workflow, client_id)
                prompt_id = res["prompt_id"]
                print(f"[+] Generation started! Prompt ID: {prompt_id}")

                # 5. Wait for generation to finish
                print("[+] Waiting for ComfyUI execution...")
                hist = poll_history(prompt_id)
                output_url, is_video = extract_output_url(hist)

                if not output_url:
                    raise RuntimeError("No image or video was produced by the ComfyUI workflow.")

                print(f"[+] Completed! Output: {output_url} (isVideo={is_video})")

                # 6. Download raw output and generate framed media
                ext = ".mp4" if is_video else ".png"
                raw_filename = f"raw_{gen_id}{ext}"
                raw_filepath = os.path.join(OUTPUTS_DIR, raw_filename)

                print(f"[+] Caching generated asset locally: {raw_filename}...")
                try:
                    urllib.request.urlretrieve(output_url, raw_filepath)
                except Exception as e:
                    print(f"[-] Could not cache remote asset: {e}")

                # Magic byte inspection: detect if asset is MP4 video
                if os.path.exists(raw_filepath):
                    try:
                        with open(raw_filepath, "rb") as f_chk:
                            hdr = f_chk.read(32)
                        if b"ftyp" in hdr or b"moov" in hdr:
                            is_video = True
                            if not raw_filename.endswith(".mp4"):
                                new_raw_filename = f"raw_{gen_id}.mp4"
                                new_raw_filepath = os.path.join(OUTPUTS_DIR, new_raw_filename)
                                os.rename(raw_filepath, new_raw_filepath)
                                raw_filename = new_raw_filename
                                raw_filepath = new_raw_filepath
                                print(f"[+] Verified asset is MP4 video: {raw_filename}")
                    except Exception as e:
                        print(f"[-] Magic byte check failed: {e}")

                framed_video_filename = f"framed_{gen_id}.mp4"
                framed_img_filename = f"framed_{gen_id}.png"
                framed_video_path = os.path.join(OUTPUTS_DIR, framed_video_filename)
                framed_img_path = os.path.join(OUTPUTS_DIR, framed_img_filename)
                framed_ready = False

                if os.path.exists(raw_filepath):
                    try:
                        print(f"[+] Generating commemorative framed media for '{creator_name}'...")
                        generate_framed_media(
                            raw_filepath=raw_filepath,
                            is_video=is_video,
                            sketch_path=sketch_saved_path,
                            creator_name=creator_name,
                            out_video_path=framed_video_path,
                            out_poster_path=framed_img_path
                        )
                        framed_ready = True
                        print(f"[+] Framed media successfully rendered!")
                    except Exception as e:
                        print(f"[-] Framed media generation error: {e}")

                local_ip = get_local_ip()
                client_host = self.headers.get("Host") or f"{local_ip}:{PORT}"
                base_url = f"http://{client_host}"
                share_url = f"http://{local_ip}:{PORT}/share?id={gen_id}"

                resp_data = {
                    "imageUrl": f"{base_url}/outputs/{raw_filename}" if not is_video else output_url,
                    "videoUrl": f"{base_url}/outputs/{raw_filename}" if is_video else None,
                    "rawVideoUrl": f"{base_url}/outputs/{raw_filename}" if (os.path.exists(raw_filepath) and is_video) else output_url,
                    "rawImageUrl": f"{base_url}/outputs/{raw_filename}" if (os.path.exists(raw_filepath) and not is_video) else output_url,
                    "framedVideoUrl": f"{base_url}/outputs/{framed_video_filename}" if (framed_ready and is_video) else None,
                    "framedImageUrl": f"{base_url}/outputs/{framed_img_filename}" if framed_ready else None,
                    "isVideo": is_video,
                    "shareUrl": share_url,
                    "creatorName": creator_name,
                    "genId": gen_id
                }

                resp_bytes = json.dumps(resp_data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                try:
                    self.wfile.write(resp_bytes)
                except (BrokenPipeError, ConnectionResetError):
                    print("[-] Client disconnected before response could be written.")

            except (BrokenPipeError, ConnectionResetError):
                print("[-] Client aborted or closed connection during generation.")
                return
            except Exception as e:
                print(f"[-] Error: {e}")
                try:
                    err_bytes = json.dumps({"error": str(e)}).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err_bytes)))
                    self.end_headers()
                    self.wfile.write(err_bytes)
                except Exception:
                    pass
        elif clean_path == "/reframe":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(content_length)
                req_data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                gen_id = req_data.get("id", "")
                new_name = (req_data.get("creator_name") or "BMU CREATOR").strip().upper()

                raw_video_path = os.path.join(OUTPUTS_DIR, f"raw_{gen_id}.mp4")
                raw_img_path = os.path.join(OUTPUTS_DIR, f"raw_{gen_id}.png")
                is_video = os.path.exists(raw_video_path)
                raw_filepath = raw_video_path if is_video else raw_img_path
                framed_video_path = os.path.join(OUTPUTS_DIR, f"framed_{gen_id}.mp4")
                framed_img_path = os.path.join(OUTPUTS_DIR, f"framed_{gen_id}.png")
                sketch_path = os.path.join(OUTPUTS_DIR, f"sketch_{gen_id}.png")
                if not os.path.exists(sketch_path):
                    sketch_path = os.path.join(BASE_DIR, "last_drawing.png")

                if os.path.exists(raw_filepath):
                    generate_framed_media(
                        raw_filepath=raw_filepath,
                        is_video=is_video,
                        sketch_path=sketch_path,
                        creator_name=new_name,
                        out_video_path=framed_video_path,
                        out_poster_path=framed_img_path
                    )
                    print(f"[+] Re-framed media for gen_id '{gen_id}' with name '{new_name}'")

                local_ip = get_local_ip()
                client_host = self.headers.get("Host") or f"{local_ip}:{PORT}"
                base_url = f"http://{client_host}"
                reframe_res = {
                    "success": True,
                    "framedVideoUrl": f"{base_url}/outputs/framed_{gen_id}.mp4?t={int(time.time())}" if is_video else None,
                    "framedImageUrl": f"{base_url}/outputs/framed_{gen_id}.png?t={int(time.time())}"
                }
                resp_bytes = json.dumps(reframe_res).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)
            except Exception as e:
                print(f"[-] Reframe error: {e}")
                err_bytes = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_bytes)))
                self.end_headers()
                try:
                    self.wfile.write(err_bytes)
                except Exception:
                    pass
        else:
            self.send_error(404, "Not Found")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

def run():
    server = HTTPServer(("0.0.0.0", PORT), KioskHandler)
    local_ip = get_local_ip()
    print(f"============================================================")
    print(f" Sketch-to-Art Kiosk Server (Running on 0.0.0.0:{PORT})")
    print(f" - Local machine:   http://localhost:{PORT}")
    print(f" - Network / Tablet: http://{local_ip}:{PORT}")
    print(f" - Target ComfyUI:  {COMFYUI_HOST}")
    print(f" - Workflow file:   {WORKFLOW_API_PATH}")
    print(f"============================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()

if __name__ == "__main__":
    run()
