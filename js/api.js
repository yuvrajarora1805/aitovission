/* Backend adapter — the ONLY file the backend integration needs to touch.
 *
 * Contract used by the UI:
 *   SketchAPI.generateImage({ drawing, drawingDataUrl, style, signal })
 *     drawing        Blob  (PNG, 1024x1024, white background)
 *     drawingDataUrl string (same PNG as a data: URL)
 *     style          'storybook' | 'watercolor' | '3d-cartoon' | 'anime' | 'realistic'
 *     signal         AbortSignal (aborted if the person starts drawing again)
 *   resolves to { imageUrl, shareUrl }
 *     imageUrl  URL (or data: URL) of the generated image. If it is on another
 *               origin, serve it with CORS headers so "Download sketch + art" works.
 *     shareUrl  public URL encoded in the QR code; should open a page where the
 *               visitor can download both the sketch and the artwork.
 *
 * Mock mode is on unless the page is opened with ?api=http://host:port
 * (or you set baseUrl below). The real call is POST {baseUrl}/generate as
 * multipart/form-data with fields "drawing" (file) and "style".
 */
window.SketchAPI = (() => {
  const params = new URLSearchParams(location.search);
  const API_CONFIG = {
    baseUrl: params.get('api') || (location.port === '8000' ? location.origin : ''),   // e.g. 'http://localhost:8000'
    mockDelayMs: 3500,
  };

  async function generateImage({ drawing, drawingDataUrl, style, signal }) {
    if (!API_CONFIG.baseUrl) return mockGenerate({ drawingDataUrl, style, signal });

    const form = new FormData();
    form.append('drawing', drawing, 'drawing.png');
    form.append('style', style);
    const creatorName = (document.querySelector('#creatorName')?.textContent || 'YUVRAJ').trim();
    form.append('creator_name', creatorName);

    const res = await fetch(`${API_CONFIG.baseUrl}/generate`, { method: 'POST', body: form, signal });
    if (!res.ok) throw new Error(`The art server replied ${res.status}. Please try again.`);
    const data = await res.json();
    return {
      ...data,
      imageUrl: data.imageUrl ?? data.image_url,
      videoUrl: data.videoUrl ?? data.video_url,
      framedVideoUrl: data.framedVideoUrl ?? data.videoUrl ?? data.imageUrl,
      framedImageUrl: data.framedImageUrl ?? data.imageUrl,
      shareUrl: data.shareUrl ?? data.share_url,
      isVideo: Boolean(data.isVideo || (data.videoUrl && (data.videoUrl.includes('.mp4') || data.videoUrl.includes('.webm')))),
    };
  }

  /* ---------- Mock: fakes an "AI" image from the sketch so the UI can be demoed ---------- */

  const PALETTES = {
    storybook:   ['#fde68a', '#fca5a5', '#93c5fd'],
    watercolor:  ['#bae6fd', '#fbcfe8', '#d9f99d'],
    '3d-cartoon':['#a5b4fc', '#f0abfc', '#fdba74'],
    anime:       ['#c4b5fd', '#fda4af', '#67e8f9'],
    realistic:   ['#cbd5e1', '#a7f3d0', '#fcd34d'],
  };

  function wait(ms, signal) {
    return new Promise((resolve, reject) => {
      const t = setTimeout(resolve, ms);
      signal?.addEventListener('abort', () => {
        clearTimeout(t);
        reject(new DOMException('Aborted', 'AbortError'));
      }, { once: true });
    });
  }

  function loadImage(src) {
    return new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => res(img);
      img.onerror = rej;
      img.src = src;
    });
  }

  async function mockGenerate({ drawingDataUrl, style, signal }) {
    await wait(API_CONFIG.mockDelayMs, signal);
    const sketch = await loadImage(drawingDataUrl);
    const N = 1024;
    const c = document.createElement('canvas');
    c.width = N; c.height = N;
    const g = c.getContext('2d');
    const [a, b, d] = PALETTES[style] || PALETTES.storybook;

    const bg = g.createLinearGradient(0, 0, N, N);
    bg.addColorStop(0, a); bg.addColorStop(0.55, b); bg.addColorStop(1, d);
    g.fillStyle = bg;
    g.fillRect(0, 0, N, N);

    for (let i = 0; i < 14; i++) {
      g.globalAlpha = 0.18;
      g.fillStyle = [a, b, d, '#ffffff'][i % 4];
      g.beginPath();
      g.arc(Math.random() * N, Math.random() * N, 80 + Math.random() * 220, 0, Math.PI * 2);
      g.fill();
    }
    g.globalAlpha = 1;

    g.filter = 'blur(10px)';
    g.globalCompositeOperation = 'multiply';
    g.globalAlpha = 0.35;
    g.drawImage(sketch, 0, 0, N, N);
    g.filter = 'none';
    g.globalAlpha = 1;
    g.drawImage(sketch, 0, 0, N, N);
    g.globalCompositeOperation = 'source-over';

    g.fillStyle = 'rgba(0,0,0,.45)';
    g.fillRect(0, N - 56, N, 56);
    g.fillStyle = '#fff';
    g.font = '600 26px Inter, sans-serif';
    g.textAlign = 'center';
    g.fillText(`MOCK PREVIEW · ${style}`, N / 2, N - 20);

    const id = Math.random().toString(36).slice(2, 10);
    return {
      imageUrl: c.toDataURL('image/png'),
      shareUrl: `https://example.com/share/${id}`,
    };
  }

  return { generateImage, config: API_CONFIG };
})();
