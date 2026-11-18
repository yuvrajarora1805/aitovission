#!/usr/bin/env python3
"""
Diagnostic script to manually check ComfyUI endpoints for an image.
Usage:
    python3 test_comfy.py
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import uuid

COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "http://10.7.5.109:8188")
IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_drawing.png")

def test_endpoint(name, method, url, data=None, headers=None):
    print(f"\n" + "="*50)
    print(f"[*] Testing: {name}")
    print(f"[*] {method} {url}")
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read()
            print(f"[✓] Status Code: {resp.status}")
            print(f"[✓] Response Headers: Content-Type: {resp.headers.get('Content-Type')}")
            try:
                parsed = json.loads(content.decode("utf-8"))
                print(f"[✓] JSON Response:\n{json.dumps(parsed, indent=2)[:500]}")
                return parsed
            except Exception:
                print(f"[✓] Binary/Raw Response Length: {len(content)} bytes")
                return content
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[✗] HTTP {e.code} Error: {err_body}")
        try:
            parsed = json.loads(err_body)
            print(f"[✗] Formatted Error Details:\n{json.dumps(parsed, indent=2)}")
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[✗] Failed: {e}")
        return None

def main():
    print(f"ComfyUI Diagnostic & Manual Endpoint Inspector")
    print(f"Target: {COMFYUI_HOST}")
    print(f"Image:  {IMAGE_PATH}")

    # 1. System stats
    test_endpoint("1. Server Status & Device Info", "GET", f"{COMFYUI_HOST}/system_stats")

    # 2. Check Queue
    test_endpoint("2. Current Queue Status", "GET", f"{COMFYUI_HOST}/queue")

    # 3. Upload last_drawing.png
    if not os.path.exists(IMAGE_PATH):
        print(f"\n[!] File not found: {IMAGE_PATH}")
        return

    with open(IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    boundary = uuid.uuid4().hex
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="image"; filename="manual_test.png"\r\n')
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(img_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
    body.extend(b"true\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    upload_result = test_endpoint(
        "3. Upload Image (/upload/image)",
        "POST",
        f"{COMFYUI_HOST}/upload/image",
        data=body,
        headers=headers
    )

    uploaded_name = upload_result.get("name", "manual_test.png") if isinstance(upload_result, dict) else "manual_test.png"

    # 4. View / Verify the image from ComfyUI
    view_url = f"{COMFYUI_HOST}/view?filename={urllib.parse.quote(uploaded_name)}&type=input"
    test_endpoint("4. View Uploaded Image (/view)", "GET", view_url)

    # 5. Check History & try to extract workflow_api.json if a prompt was previously executed
    history = test_endpoint("5. Check Execution History (/history)", "GET", f"{COMFYUI_HOST}/history")
    if isinstance(history, dict) and history:
        print(f"\n[*] Found {len(history)} executions in ComfyUI history.")
        last_id = list(history.keys())[-1]
        last_item = history[last_id]
        prompt_data = last_item.get("prompt", [])
        if len(prompt_data) > 2 and isinstance(prompt_data[2], dict):
            api_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_api.json")
            with open(api_file, "w", encoding="utf-8") as f:
                json.dump(prompt_data[2], f, indent=2)
            print(f"\n[🎉 SUCCESS!] Auto-extracted 'workflow_api.json' from your last ComfyUI execution!")
            print(f"Saved to: {api_file}")

    # 6. Test Queue Prompt (/prompt) with workflow_api.json
    api_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_api.json")
    if os.path.exists(api_file):
        with open(api_file, "r", encoding="utf-8") as f:
            wf = json.load(f)
        # Update image to manual_test.png
        for nid, node in wf.items():
            if node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = uploaded_name
                break
        payload = json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode("utf-8")
        test_endpoint("6. Test Queue Prompt (/prompt)", "POST", f"{COMFYUI_HOST}/prompt", data=payload, headers={"Content-Type": "application/json"})

    print("\n" + "="*50)
    print("Done testing endpoints!")

if __name__ == "__main__":
    main()

