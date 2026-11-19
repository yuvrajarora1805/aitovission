# BMU Founder's Day — AI Sketch-to-Video Kiosk 🎨✨

An interactive, live AI kiosk software built for BML Munjal University's Founder's Day exhibition. Visitors draw on a digital sketch pad, and generative AI transforms their sketches into high-definition 3D volumetric animated artwork videos set inside an official commemorative BMU Founder's Day frame.

Visitors can instantly scan a QR code with their mobile phone to download and take home their commemorative video.

---

## 🌟 Key Features

* **Interactive Sketch Pad**: Natural pressure-sensitive pen, brush size slider, color palette, eraser, and undo. Works with Wacom/drawing tablets, touch screens, and mouse input.
* **Smart 5-Second Wait Timer**: Gives visitors time to finish their drawing. After the pen is lifted for **5 seconds**, it automatically triggers generation. Drawing again resets the timer immediately.
* **Personalized Artist Name Prompt**: Prompts the artist for their name (or allows entering it via the top header), beautifully printing `CREATED BY: <NAME>` on their final video, photo, and certificate.
* **MiniMax H3 Image-to-Video**: Direct ComfyUI GPU integration transforming line sketches into living animated art.
* **Official BMU Founder's Day Frame**: Features the BMU SAAR logo, Picture-in-Picture (PIP) sketch badge, and artist attribution.
* **Edge-to-Edge Cover Fit**: Clean video composition without white sidebars or pillarbox bars.
* **Live In-Place Name Re-framing**: Editing the artist's name on the kiosk result screen automatically re-renders the video and QR code in the background (~0.3s).
* **Instant Mobile QR Download**: Automatically generates a QR code pointing to `/share?id=...` where visitors can watch and download their video directly onto their phone.

---

## 📐 System Architecture

```text
[ Kiosk Frontend ] ──(Port 8000 or XAMPP:80)──> [ comfy_bridge.py ] ──(Port 8190)──> [ ComfyUI GPU Server ]
   HTML5 / Canvas                               Local Python Server                     MiniMax H3 Workflow
   Full-screen UI                              • Receives drawing PNG                  • LoadImage
                                               • Uploads to ComfyUI                    • MiniMaxH3ImageToVideo
                                               • Polls execution                       • VideoCombine (MP4)
                                               • Composites BMU Frame (FFmpeg)
                                               • Serves /share mobile page
```

---

## 🛠️ Prerequisites

### On the Kiosk Machine:

#### 🪟 Windows Setup (Quick 1-Click):
1. **Install Python 3.9+** from [python.org](https://www.python.org/downloads/) *(check **"Add python.exe to PATH"** during install)*.
2. **Install FFmpeg** on Windows using PowerShell:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   *(Or download from [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and add its `bin` folder to Windows Environment Variables PATH).*
3. **Run the Automated Installer**:
   Double-click `setup.bat` (or in CMD run: `pip install -r requirements.txt`).
4. **Launch the Bridge**:
   Double-click `run_bridge.bat` (or in CMD run: `python comfy_bridge.py`).

#### 🐧 Linux (Debian / Kali / Ubuntu):
1. **Run the automated setup script**:
   ```bash
   chmod +x setup.sh && ./setup.sh
   ```
   *(Or manually: `sudo apt install -y ffmpeg fonts-dejavu-core && pip install -r requirements.txt`)*
2. **Launch the Bridge**:
   ```bash
   python3 comfy_bridge.py
   ```

### On the GPU Machine (Running ComfyUI):
* ComfyUI with MiniMax H3 Image-to-Video custom nodes installed.
* Network access enabled between the Kiosk and the GPU machine.

---

## 🚀 Complete Step-by-Step Setup Guide

### Step 1: Start ComfyUI on the GPU Server
ComfyUI must listen on all network interfaces (`0.0.0.0`) so the kiosk machine can connect to it.

On the GPU machine, launch ComfyUI on port `8190`:
```bash
python main.py --listen 0.0.0.0 --port 8190
```
*(Verify by running `ss -tulpn | grep 8190` or visiting `http://<GPU_IP>:8190` in your browser).*

---

### Step 2: Clone & Configure on the Kiosk Machine

1. **Clone the repository**:
   ```bash
   cd "/media/yuvraj/New Volume/xamp/htdocs"
   git clone https://github.com/yuvrajarora1805/aitovission.git aidtovid
   cd aidtovid
   ```

2. **Verify Configuration**:
   Inside `comfy_bridge.py`, the default ComfyUI server address is set to:
   ```python
   COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "http://10.7.5.109:8190")
   PORT = int(os.environ.get("PORT", 8000))
   ```
   If your GPU machine's IP is different, you can pass it as an environment variable when launching:
   ```bash
   COMFYUI_HOST=http://<YOUR_GPU_IP>:8190 python3 comfy_bridge.py
   ```

---

### Step 3: Start the Bridge Server

Run the bridge server in your terminal:
```bash
python3 comfy_bridge.py
```
You will see:
```text
======================================================================
  BMU Founder's Day — Sketch-to-Art Kiosk Bridge
======================================================================
  * Bridge Server : http://0.0.0.0:8000
  * Local Access  : http://127.0.0.1:8000
  * Network Access: http://10.7.5.109:8000
  * ComfyUI Target: http://10.7.5.109:8190
  * Workflow File : .../workflow_api.json (Found)
======================================================================
```

---

### Step 4: Open the Kiosk UI

Open your browser (Google Chrome recommended) and navigate to:
```text
http://localhost:8000/
```
*(Or via XAMPP Apache: `http://localhost/aidtovid/`)*

* Press <kbd>F</kbd> (or click the fullscreen icon at top right) to put the kiosk in fullscreen kiosk mode.

---

## 🎨 Kiosk Visitor Experience

1. **Draw**: The visitor draws their sketch on the left canvas.
2. **Countdown (5s)**: When they lift their pen, a 5-second countdown ring appears. If they touch the canvas again, the timer pauses and resets.
3. **Name Prompt**: If they haven't typed their name in the header, a popup appears:  
   > *"Who created this art? Enter your name to appear on your commemorative Founder's Day video."*  
   They type their name and press <kbd>Enter</kbd> (or tap **"Create My Art ✨"**).
4. **Processing Animation**: Shows artistic status updates with an elapsed timer while the GPU renders.
5. **Artwork Display**: The commemorative artwork video plays in an edge-to-edge frame on the right side.
6. **Take Home via QR Code**: The visitor scans the on-screen QR code with their smartphone camera, opening the `/share` page to watch and download their video directly.
7. **New Visitor**: Clicking **"＋ New drawing"** clears the pad and resets the artist name for the next visitor.

---

## ⌨️ Operator Shortcuts

| Key | Action | Description |
| :--- | :--- | :--- |
| <kbd>F</kbd> | Fullscreen | Toggle fullscreen mode |
| <kbd>G</kbd> | Generate Now | Skip the 5s timer and generate immediately |
| <kbd>Delete</kbd> / <kbd>N</kbd> | New Drawing | Clear the canvas & reset artist name for the next visitor |
| <kbd>Ctrl</kbd> + <kbd>Z</kbd> | Undo | Undo last stroke |
| <kbd>P</kbd> | Pen | Switch to drawing pen |
| <kbd>E</kbd> | Eraser | Switch to eraser |
| <kbd>Esc</kbd> | Close Modal | Close QR code or name popup |

---

## ⚙️ URL Parameters

You can customize the kiosk behavior directly via URL query parameters:
* `?delay=5000`: Set idle countdown delay in milliseconds (default is `5000` / 5 sec).
* `?api=http://10.7.5.109:8000`: Point to a custom bridge server origin.
* `?mock=1`: Run in mock test mode without sending requests to the GPU.

---

## 🔧 Troubleshooting

### 1. `<urlopen error [Errno 111] Connection refused>`
* **Reason**: `comfy_bridge.py` cannot reach ComfyUI on port `8190`.
* **Fix**:
  1. Confirm ComfyUI is running on the GPU host: `ss -tulpn | grep 8190`
  2. Verify ComfyUI was launched with `--listen 0.0.0.0 --port 8190` (not just localhost).
  3. Verify the GPU host IP hasn't changed with `hostname -I`.
  4. Test connectivity from the kiosk machine: `curl -I http://10.7.5.109:8190`

### 2. ComfyUI Output Treated as Blank / Not Video
* `comfy_bridge.py` automatically checks filename extensions (`.mp4`, `.webm`) and inspects file header magic bytes (`ftyp`, `moov`) to detect video files produced by ComfyUI's combine nodes.

### 3. QR Code Download Access
* The QR code encodes `http://<KIOSK_LOCAL_IP>:8000/share?id=...`. Ensure the phone and kiosk are connected to the same local Wi-Fi network so the phone can reach port 8000.

---

## 📦 Creating a Clean Backup ZIP
To create a clean zip archive of the project without temporary videos and git folders:
```bash
zip -r aidtovid_backup.zip . -x ".git/*" "outputs/*" "__pycache__/*" "*.zip"
```
