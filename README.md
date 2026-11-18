# Sketch to Art — kiosk UI

Left side: a live drawing canvas (works with a pen tablet, including pressure, as well as a mouse or touch).
Right side: the AI artwork. When the person lifts their pen and pauses, the sketch is sent for generation automatically. The result shows a download button and a QR code.

## Run it

```bash
python -m http.server 5500
```

Open http://localhost:5500, then press **F** for fullscreen.

URL options:
- `?delay=3000`: how long the pen must stay lifted before generating (ms). The default is 3000.
- `?api=http://localhost:8000`: use the real backend. Without it, the UI runs in **mock mode**.

## For the backend

Only `js/api.js` talks to the server. The UI calls:

```
POST {api}/generate      multipart/form-data
  drawing  PNG file, 1024x1024, white background
  style    storybook | watercolor | 3d-cartoon | anime | realistic

200 → { "imageUrl": "...", "shareUrl": "..." }     (snake_case is also accepted)
```

- `imageUrl` is the generated image. If it is served from another origin, send `Access-Control-Allow-Origin` so the browser can build the combined "sketch + art" download.
- `shareUrl` is encoded in the QR code. It should open a phone-friendly page where people can download both their sketch and the artwork.
- When the person starts drawing again, the request is aborted (`AbortController`) and a new one is sent after the next pause.

## Operator shortcuts

| Key | Action |
| --- | --- |
| F | Fullscreen |
| G | Generate now |
| N / Delete | New drawing (clear) |
| Ctrl+Z | Undo |
| P / E | Pen / Eraser |
| Esc | Close the QR popup |

The QR code library loads from a CDN (jsDelivr). If the venue has no internet, download `qrcode.min.js` into `js/` and change the `<script>` tag in `index.html`.
