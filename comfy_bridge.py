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
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler

COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "http://10.7.5.109:8188")
PORT = int(os.environ.get("PORT", 8000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
            params = urllib.parse.urlencode({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")
            })
            return f"{COMFYUI_HOST}/view?{params}", False
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

                if not drawing_bytes:
                    self.send_error(400, "Missing 'drawing' file")
                    return

                # 1. Upload sketch to ComfyUI
                filename = f"sketch_{int(time.time())}.png"
                
                # Save a local copy for debugging so you can inspect the exact image sent
                local_debug_path = os.path.join(BASE_DIR, "last_drawing.png")
                with open(local_debug_path, "wb") as f_debug:
                    f_debug.write(drawing_bytes)

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

                # Enforce parameters: set 5.0s duration, 0.88 denoise; preserve workflow megapixels if specified
                if "7:133" in workflow:
                    workflow["7:133"]["inputs"]["value"] = 5.0
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

                resp_data = {
                    "imageUrl": output_url,
                    "videoUrl": output_url if is_video else None,
                    "isVideo": is_video,
                    "shareUrl": output_url
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_data).encode("utf-8"))

            except Exception as e:
                print(f"[-] Error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_msg = json.dumps({"error": str(e)})
                self.wfile.write(err_msg.encode("utf-8"))
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
