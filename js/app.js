/* Sketch to Art — front-end controller.
 * Draw on the left canvas; once the pen has been lifted for CONFIG.idleDelayMs
 * the sketch is sent to SketchAPI.generateImage (see js/api.js) and the result
 * is shown on the right with download buttons and a QR code.
 */
(() => {
  const params = new URLSearchParams(location.search);

  const CONFIG = {
    idleDelayMs: Number(params.get('delay')) || 5000, // pause after pen lift before generating (5s)
    minInkPoints: 8,                                   // ignore accidental taps
    eraserScale: 3,
    colors: ['#111827', '#ef4444', '#f97316', '#facc15', '#22c55e', '#06b6d4', '#3b82f6', '#a855f7', '#ec4899', '#92400e'],
    styles: [
      { id: 'storybook', label: 'Storybook' },
      { id: 'watercolor', label: 'Watercolor' },
      { id: '3d-cartoon', label: '3D Cartoon' },
      { id: 'anime', label: 'Anime' },
      { id: 'realistic', label: 'Realistic' },
    ],
    loadingMessages: [
      'Mixing the paints…',
      'Reading your lines…',
      'Adding colour and light…',
      'Sprinkling a little magic…',
      'Almost there…',
    ],
  };

  const $ = (sel) => document.querySelector(sel);
  const board = $('#board');
  const ctx = board.getContext('2d');
  const outputBody = $('#outputBody');

  const state = {
    strokes: [],
    current: null,
    tool: 'pen',
    color: CONFIG.colors[0],
    size: 8,
    style: CONFIG.styles[0].id,
    view: 'empty',
    generation: 0,      // bumped on every new request so stale responses are ignored
    abort: null,
    result: null,       // { imageUrl, shareUrl, sketchUrl }
    timers: {},
  };

  /* ---------------- Drawing ---------------- */

  const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, p: (a.p + b.p) / 2 });
  const colorOf = (s) => (s.tool === 'eraser' ? '#ffffff' : s.color);
  const widthFor = (s, p) => {
    const base = s.tool === 'eraser' ? s.size * CONFIG.eraserScale : s.size;
    return base * (0.35 + p * 1.3); // pressure 0.5 (mouse) => 1x
  };

  function toBoard(e) {
    const r = board.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) * board.width) / r.width,
      y: ((e.clientY - r.top) * board.height) / r.height,
      p: e.pointerType === 'pen' && e.pressure > 0 ? e.pressure : 0.5,
    };
  }

  function drawDot(s, pt) {
    ctx.fillStyle = colorOf(s);
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, widthFor(s, pt.p) / 2, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawSegment(s, i) {
    const pts = s.points;
    const p1 = pts[i - 1];
    const p2 = pts[i];
    const p0 = pts[i - 2] || p1;
    const m1 = mid(p0, p1);
    const m2 = mid(p1, p2);
    ctx.strokeStyle = colorOf(s);
    ctx.lineWidth = widthFor(s, p2.p);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(m1.x, m1.y);
    ctx.quadraticCurveTo(p1.x, p1.y, m2.x, m2.y);
    ctx.stroke();
  }

  function drawTail(s) {
    const pts = s.points;
    if (pts.length < 2) return;
    const a = mid(pts[pts.length - 2], pts[pts.length - 1]);
    const b = pts[pts.length - 1];
    ctx.strokeStyle = colorOf(s);
    ctx.lineWidth = widthFor(s, b.p);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  function drawStroke(s) {
    drawDot(s, s.points[0]);
    for (let i = 1; i < s.points.length; i++) drawSegment(s, i);
    drawTail(s);
  }

  function redraw() {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, board.width, board.height);
    state.strokes.forEach(drawStroke);
  }

  function inkAmount() {
    return state.strokes
      .filter((s) => s.tool === 'pen')
      .reduce((n, s) => n + s.points.length, 0);
  }
  const hasInk = () => inkAmount() >= CONFIG.minInkPoints;

  board.addEventListener('pointerdown', (e) => {
    if (e.button > 0 && e.pointerType === 'mouse') return;
    e.preventDefault();
    board.setPointerCapture(e.pointerId);
    const s = { tool: state.tool, color: state.color, size: state.size, points: [toBoard(e)] };
    state.current = s;
    state.strokes.push(s);
    drawDot(s, s.points[0]);
    onStrokeStart();
  });

  board.addEventListener('pointermove', (e) => {
    const s = state.current;
    if (!s) return;
    const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const ev of events.length ? events : [e]) {
      s.points.push(toBoard(ev));
      drawSegment(s, s.points.length - 1);
    }
  });

  const endStroke = () => {
    if (!state.current) return;
    drawTail(state.current);
    state.current = null;
    onStrokeEnd();
  };
  board.addEventListener('pointerup', endStroke);
  board.addEventListener('pointercancel', endStroke);

  /* ---------------- Flow: draw → pause → generate ---------------- */

  function onStrokeStart() {
    cancelPending();
    $('#canvasHint').classList.add('is-hidden');
    $('#liveBadge').classList.add('is-on');
    setView('drawing');
  }

  function onStrokeEnd() {
    $('#liveBadge').classList.remove('is-on');
    if (hasInk()) scheduleGenerate();
    else setView(state.strokes.length ? 'drawing' : 'empty');
  }

  function cancelPending() {
    clearTimeout(state.timers.idle);
    clearInterval(state.timers.countdown);
    if (state.abort) state.abort.abort();
    state.abort = null;
    state.generation++;
  }

  function scheduleGenerate() {
    cancelPending();
    setView('countdown');
    const fill = $('#ringFill');
    fill.style.setProperty('--dur', CONFIG.idleDelayMs + 'ms');
    fill.classList.remove('is-running');
    void fill.getBoundingClientRect(); // restart the CSS animation
    fill.classList.add('is-running');

    const endsAt = performance.now() + CONFIG.idleDelayMs;
    const tick = () => {
      $('#countdownNum').textContent = Math.max(1, Math.ceil((endsAt - performance.now()) / 1000));
    };
    tick();
    state.timers.countdown = setInterval(tick, 100);
    state.timers.idle = setTimeout(generate, CONFIG.idleDelayMs);
  }

  async function generate() {
    cancelPending();
    if (!hasInk()) return;

    const gen = state.generation;
    const controller = new AbortController();
    state.abort = controller;

    const sketchUrl = board.toDataURL('image/png');
    $('#magicSketch').src = sketchUrl;
    setView('generating');

    try {
      const blob = await new Promise((res) => board.toBlob(res, 'image/png'));
      const res = await SketchAPI.generateImage({
        drawing: blob,
        drawingDataUrl: sketchUrl,
        style: state.style,
        signal: controller.signal,
      });
      if (gen !== state.generation) return;
      await preload(res.imageUrl);
      if (gen !== state.generation) return;
      state.result = { ...res, sketchUrl };
      showResult();
    } catch (err) {
      if (err.name === 'AbortError' || gen !== state.generation) return;
      console.error(err);
      $('#errorText').textContent = err.message || 'Something went wrong while creating your artwork.';
      setView('error');
    } finally {
      if (gen === state.generation) state.abort = null;
    }
  }

  function preload(src) {
    return new Promise((resolve) => {
      if (!src) return resolve(null);
      if (src.includes('.mp4') || src.includes('.webm') || src.includes('video/')) {
        const vid = document.createElement('video');
        vid.crossOrigin = 'anonymous';
        vid.muted = true;
        vid.playsInline = true;
        vid.src = src;
        vid.onloadeddata = () => {
          try { vid.currentTime = 0.1; } catch (e) { resolve(vid); }
        };
        vid.onseeked = () => resolve(vid);
        vid.onerror = () => resolve(vid);
        vid.load();
        setTimeout(() => resolve(vid), 2500);
        return;
      }
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = src;
    });
  }

  function showResult() {
    const r = state.result;
    const isVid = r.isVideo || (r.imageUrl && (r.imageUrl.includes('.mp4') || r.imageUrl.includes('.webm') || r.imageUrl.includes('video/')));
    const vidEl = $('#resultVideo');
    if (isVid && vidEl) {
      $('#resultImg').style.display = 'none';
      vidEl.style.display = 'block';
      vidEl.src = r.videoUrl || r.imageUrl;
      vidEl.play().catch(() => {});
    } else {
      if (vidEl) vidEl.style.display = 'none';
      $('#resultImg').style.display = 'block';
      $('#resultImg').src = r.imageUrl;
    }
    $('#sketchThumb').src = r.sketchUrl;
    $('#modalSketch').src = r.sketchUrl;
    $('#modalArt').src = r.imageUrl;
    $('#shareUrl').textContent = r.shareUrl || '';
    renderQR($('#qrInline'), r.shareUrl, 4);
    renderQR($('#qrBig'), r.shareUrl, 8);
    setView('result');
  }

  /* ---------------- Views ---------------- */

  const STATUS = {
    empty: ['Ready', 'idle'],
    drawing: ['Drawing…', 'live'],
    countdown: ['Waiting for pause', 'wait'],
    generating: ['Creating art', 'busy'],
    result: ['Done!', 'done'],
    error: ['Error', 'error'],
  };

  function setView(view) {
    if (state.view === 'generating' && view !== 'generating') stopLoading();
    state.view = view;
    outputBody.dataset.view = view;
    const [text, tone] = STATUS[view];
    $('#statusText').textContent = text;
    $('#statusPill').dataset.tone = tone;

    if (view === 'empty') {
      $('#emptyEmoji').textContent = '🎨';
      $('#emptyTitle').textContent = 'Your artwork will appear here';
      $('#emptyText').textContent = 'Draw on the pad. When you lift your pen, the magic starts.';
    } else if (view === 'drawing') {
      $('#emptyEmoji').textContent = '✏️';
      $('#emptyTitle').textContent = 'Looking good, keep going!';
      $('#emptyText').textContent = 'Lift your pen when you are done and we will turn it into art.';
    } else if (view === 'generating') {
      startLoading();
    }
    $('#generateNowBtn').disabled = view === 'generating';
  }

  function startLoading() {
    let i = 0;
    const started = performance.now();
    $('#loadingMsg').textContent = CONFIG.loadingMessages[0];
    state.timers.msg = setInterval(() => {
      i = Math.min(i + 1, CONFIG.loadingMessages.length - 1);
      $('#loadingMsg').textContent = CONFIG.loadingMessages[i];
    }, 1600);
    state.timers.elapsed = setInterval(() => {
      $('#elapsed').textContent = ((performance.now() - started) / 1000).toFixed(1);
    }, 100);
  }

  function stopLoading() {
    clearInterval(state.timers.msg);
    clearInterval(state.timers.elapsed);
  }

  /* ---------------- QR + downloads ---------------- */

  function renderQR(img, text, cellSize) {
    if (!text) { img.removeAttribute('src'); return; }
    if (!window.qrcode) { img.alt = 'QR library failed to load'; return; }
    const qr = window.qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    img.src = qr.createDataURL(cellSize, 2);
  }

  function downloadUrl(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const stamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');

  async function downloadFramedVideo() {
    const r = state.result;
    if (!r) return;
    const creatorName = ($('#creatorName')?.textContent || 'YUVRAJ').trim().toUpperCase();
    const vidUrl = r.framedVideoUrl || r.videoUrl;
    if (vidUrl) {
      toast('Starting download of framed video…');
      downloadUrl(vidUrl, `BMU_Framed_Video_${creatorName}_${stamp()}.mp4`);
    } else {
      await downloadFramedPhoto();
    }
  }

  async function downloadFramedPhoto() {
    const r = state.result;
    if (!r) return;
    const creatorName = ($('#creatorName')?.textContent || 'YUVRAJ').trim().toUpperCase();

    // If server already prepared a sharp framed image:
    if (r.framedImageUrl) {
      toast('Downloading framed photo…');
      downloadUrl(r.framedImageUrl, `BMU_Framed_Photo_${creatorName}_${stamp()}.png`);
      return;
    }

    try {
      toast('Rendering commemorative frame…');
      const W = 768, H = 1024;
      const c = document.createElement('canvas');
      c.width = W; c.height = H;
      const g = c.getContext('2d');

      // 1. Royal blue background (#000fa2)
      g.fillStyle = '#000fa2';
      g.fillRect(0, 0, W, H);

      // 2. BMU SAAR Logo at top
      const logo = await preload('bmu_saar_logo_web.png').catch(() => null);
      if (logo) {
        const lw = 400;
        const lh = (logo.naturalHeight / logo.naturalWidth) * lw;
        g.drawImage(logo, (W - lw) / 2, 22, lw, lh);
      }

      // 3. Central Artwork / Video window
      const vx = 68, vy = 98, vw = 632, vh = 816;
      g.fillStyle = '#ffffff';
      g.fillRect(vx, vy, vw, vh);

      const vidEl = $('#resultVideo');
      if (vidEl && vidEl.style.display !== 'none' && vidEl.readyState >= 2) {
        g.drawImage(vidEl, vx, vy, vw, vh);
      } else if (r.imageUrl) {
        const art = await preload(r.imageUrl);
        if (art) g.drawImage(art, vx, vy, vw, vh);
      }

      // 4. Sketch PIP badge in bottom-left corner
      if (r.sketchUrl) {
        const sketch = await preload(r.sketchUrl).catch(() => null);
        if (sketch) {
          const bw = 130, bh = 130;
          const bx = vx + 16, by = vy + vh - bh - 16;
          g.fillStyle = '#ffffff';
          g.beginPath();
          g.roundRect(bx, by, bw, bh, 10);
          g.fill();
          g.strokeStyle = '#e2e8f0';
          g.lineWidth = 2;
          g.strokeRect(bx, by, bw, bh);
          g.drawImage(sketch, bx + 10, by + 8, bw - 20, bh - 36);
          g.fillStyle = '#0f172a';
          g.font = '700 11px Inter, sans-serif';
          g.textAlign = 'center';
          g.fillText('Your sketch', bx + bw / 2, by + bh - 12);
        }
      }

      // 5. Creator Name at bottom
      g.fillStyle = '#ffffff';
      g.font = '700 24px Inter, sans-serif';
      g.textAlign = 'center';
      g.fillText(`CREATED BY: ${creatorName}`, W / 2, 975);

      downloadUrl(c.toDataURL('image/png'), `BMU_Framed_Photo_${creatorName}_${stamp()}.png`);
    } catch (err) {
      console.error(err);
      toast('Downloading artwork directly.');
      downloadUrl(r.imageUrl, `BMU_Artwork_${stamp()}.png`);
    }
  }

  /* ---------------- Toolbar & controls ---------------- */

  function buildControls() {
    const chips = $('#styleChips');
    CONFIG.styles.forEach((st) => {
      const b = document.createElement('button');
      b.className = 'chip' + (st.id === state.style ? ' is-active' : '');
      b.textContent = st.label;
      b.setAttribute('role', 'radio');
      b.onclick = () => {
        state.style = st.id;
        chips.querySelectorAll('.chip').forEach((el) => el.classList.toggle('is-active', el === b));
        $('#styleLabel').textContent = 'Style: ' + st.label;
        if (hasInk() && (state.view === 'result' || state.view === 'error')) generate();
      };
      chips.appendChild(b);
    });
    $('#styleLabel').textContent = 'Style: ' + CONFIG.styles[0].label;

    const swatches = $('#colorSwatches');
    CONFIG.colors.forEach((col, i) => {
      const b = document.createElement('button');
      b.className = 'swatch' + (i === 0 ? ' is-active' : '');
      b.style.background = col;
      b.title = col;
      b.setAttribute('aria-label', 'Colour ' + col);
      b.onclick = () => {
        state.color = col;
        swatches.querySelectorAll('.swatch').forEach((el) => el.classList.toggle('is-active', el === b));
        setTool('pen');
      };
      swatches.appendChild(b);
    });

    const range = $('#sizeRange');
    range.oninput = () => { state.size = Number(range.value); updateSizePreview(); };
    updateSizePreview();

    $('#penBtn').onclick = () => setTool('pen');
    $('#eraserBtn').onclick = () => setTool('eraser');
    $('#undoBtn').onclick = undo;
    $('#clearBtn').onclick = clearBoard;
    $('#generateNowBtn').onclick = () => (hasInk() ? generate() : toast('Draw something first!'));
    $('#downloadBothBtn').onclick = downloadFramedVideo;
    $('#downloadArtBtn').onclick = downloadFramedPhoto;
    $('#regenBtn').onclick = generate;
    $('#retryBtn').onclick = generate;
    $('#newBtn').onclick = clearBoard;
    $('#qrCard').onclick = openQR;
    $('#qrClose').onclick = closeQR;
    $('#qrModal').onclick = (e) => { if (e.target.id === 'qrModal') closeQR(); };
    $('#fullscreenBtn').onclick = toggleFullscreen;

    // Creator Name Editing
    const nameEl = $('#creatorName');
    const editBtn = $('#editNameBtn');
    const savedName = localStorage.getItem('bmu_creator_name');
    if (savedName && nameEl) nameEl.textContent = savedName;

    function saveCreatorName() {
      if (!nameEl) return;
      let val = nameEl.textContent.trim();
      if (!val) val = 'YUVRAJ';
      nameEl.textContent = val;
      localStorage.setItem('bmu_creator_name', val);
    }

    if (nameEl) {
      nameEl.addEventListener('blur', saveCreatorName);
      nameEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          nameEl.blur();
        }
      });
    }

    if (editBtn && nameEl) {
      editBtn.addEventListener('click', () => {
        nameEl.focus();
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(nameEl);
        sel.removeAllRanges();
        sel.addRange(range);
      });
    }
  }

  function updateSizePreview() {
    const p = $('#sizePreview');
    p.style.setProperty('--s', Math.min(30, state.size) + 'px');
    p.style.setProperty('--c', state.tool === 'eraser' ? '#ffffff' : state.color);
  }

  function setTool(tool) {
    state.tool = tool;
    $('#penBtn').classList.toggle('is-active', tool === 'pen');
    $('#eraserBtn').classList.toggle('is-active', tool === 'eraser');
    $('#canvasWrap').classList.toggle('is-eraser', tool === 'eraser');
    updateSizePreview();
  }

  function undo() {
    if (!state.strokes.length) return;
    state.strokes.pop();
    redraw();
    if (hasInk()) scheduleGenerate();
    else clearBoard();
  }

  function clearBoard() {
    cancelPending();
    state.strokes = [];
    state.current = null;
    state.result = null;
    redraw();
    closeQR();
    $('#canvasHint').classList.remove('is-hidden');
    setView('empty');
  }

  function openQR() { if (state.result) $('#qrModal').hidden = false; }
  function closeQR() { $('#qrModal').hidden = true; }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  }

  let toastTimer;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('is-on'), 2600);
  }

  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea, [contenteditable="true"]') || e.target.isContentEditable) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); undo(); }
    else if (e.ctrlKey || e.metaKey || e.altKey) return;
    else if (k === 'escape') closeQR();
    else if (k === 'delete') clearBoard();
    else if (k === 'f') toggleFullscreen();
    else if (k === 'g') $('#generateNowBtn').click();
    else if (k === 'n') clearBoard();
    else if (k === 'p') setTool('pen');
    else if (k === 'e') setTool('eraser');
  });

  buildControls();
  redraw();
  setView('empty');
})();
