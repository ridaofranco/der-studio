/* Editor de reels de DER Studio (estilo CapCut).
 *
 * Pantalla completa: reproductor arriba, línea de tiempo con las tiras de cuadros de cada clip
 * (se recortan arrastrando los bordes), transiciones entre clips y herramientas abajo.
 * Todo se guarda como borrador en el celular a cada cambio; "Vista previa" arma una versión
 * liviana en segundos y "Exportar" la versión final en alta (sigue aunque salgas de la app).
 */
const ReelEditor = (() => {
  const OUTRO = 3, OUTRO_FADE = 0.5, MIN = 0.3, MAX_FOTO = 15, MAX_REV = 6;
  const BRAND = { naranja: "#ff5c00", oscuro: "#333333", claro: "#f0f0f0", blanco: "#ffffff", negro: "#000000" };
  const FORMATOS = { historia: "9:16", post: "4:5", cuadrado: "1:1" };
  const CSS_FILTRO = {
    ninguno: "", vivo: "saturate(1.35) contrast(1.08)", der: "sepia(.22) saturate(1.25) hue-rotate(-8deg)",
    cine: "contrast(1.15) saturate(.9) hue-rotate(-6deg)", calido: "sepia(.3) saturate(1.1)",
    frio: "hue-rotate(12deg) saturate(.9) brightness(1.02)", vintage: "sepia(.5) contrast(.9) saturate(.8)",
    suave: "contrast(.9) brightness(1.04) saturate(.9)", noche: "brightness(.85) contrast(1.2) hue-rotate(12deg)",
    bn: "grayscale(1) contrast(1.12)", bn_suave: "grayscale(1) contrast(.95) brightness(1.03)",
  };
  const I = { // íconos (trazos de 24×24)
    cortar: "M6 3v12M18 3v12M6 9l12 6M18 9 6 15M6 18a2 2 0 1 0 0 .1M18 18a2 2 0 1 0 0 .1",
    dividir: "M12 2v20M5 7h4v10H5zM15 7h4v10h-4z", velocidad: "M12 13l4-4M4 18a8 8 0 1 1 16 0",
    volumen: "M4 9v6h4l5 4V5L8 9H4zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11",
    encuadre: "M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M9 9h6v6H9z", filtro: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 3v18M3 12h18",
    ajustes: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4",
    anim: "M4 12h3l2-6 4 12 2-6h5", girar: "M20 12a8 8 0 1 1-3-6.2M20 4v5h-5", congelar: "M12 2v20M4 6l16 12M20 6 4 18",
    invertir: "M7 7h11l-3-3M17 17H6l3 3", duplicar: "M8 8h12v12H8zM4 16V4h12", borrar: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
    mover: "M5 12h14M9 8l-4 4 4 4M15 8l4 4-4 4", agregar: "M12 5v14M5 12h14", formato: "M7 3h10v18H7zM10 18h4",
    musica: "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    voz: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
    texto: "M5 5h14M12 5v14M9 19h6", logo: "M4 4h16v16H4zM8 15V9h4a3 3 0 0 1 0 6H8z",
  };
  const ico = n => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${I[n]}"/></svg>`;
  const fmt = s => (Math.round(s * 10) / 10).toLocaleString("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const tc = s => { s = Math.max(0, s); const m = Math.floor(s / 60); return `${String(m).padStart(2, "0")}:${fmt(s - m * 60).padStart(4, "0")}`; };
  const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clone = o => JSON.parse(JSON.stringify(o));
  const uid = () => Math.random().toString(36).slice(2, 10);
  const dur = c => (c.end - c.start) / (c.kind === "foto" ? 1 : c.speed || 1);

  function total(p) {
    let t = 0;
    p.clips.forEach((c, i) => {
      t += dur(c);
      if (i < p.clips.length - 1 && c.transition !== "none") t -= Math.min(c.transition_seconds, dur(c) / 2, dur(p.clips[i + 1]) / 2);
    });
    return t + (p.opciones.outro === false ? 0 : OUTRO - OUTRO_FADE);
  }

  function cssLook(c) {
    const f = [CSS_FILTRO[c.filtro] || ""];
    if (c.brillo) f.push(`brightness(${1 + c.brillo / 100 * 0.4})`);
    if (c.contraste) f.push(`contrast(${1 + c.contraste / 100 * 0.6})`);
    if (c.saturacion) f.push(`saturate(${Math.max(0, 1 + c.saturacion / 100)})`);
    if (c.temperatura) f.push(c.temperatura > 0 ? `sepia(${c.temperatura / 250})` : `hue-rotate(${-c.temperatura / 8}deg)`);
    return f.join(" ") || "none";
  }

  // ---------------------------------------------------------------------------
  // Tarjeta de resultado (en el panel Reels): video, descargar y "Editar reel"
  // ---------------------------------------------------------------------------
  function open(box, info, opts = {}) {
    const p = info.proyecto;
    box.innerHTML = `
      <div class="re-player">
        <video class="final" src="${info.archivo}" controls playsinline></video>
        <div class="acciones" style="justify-content:center">
          <a class="prim" href="${info.archivo}" download>Descargar reel (.mp4)</a>
          ${opts.compartir ? `<a href="#" class="re-sh">Compartir</a>` : ""}
        </div>
        ${p ? `<button type="button" class="rx-abrir">${ico("cortar")}<span>Editar reel</span><small>recortar, dividir, velocidad, filtros, música, voz…</small></button>` : ""}
        ${info.borrador ? `<p class="hint" style="text-align:center">Tenés cambios guardados sin exportar: se abren al editar.</p>` : ""}
      </div>`;
    if (opts.compartir) box.querySelector(".re-sh").onclick = ev => { ev.preventDefault(); opts.compartir(info.archivo); };
    if (p) box.querySelector(".rx-abrir").onclick = () => editor(info, opts, box);
  }

  // ---------------------------------------------------------------------------
  // Editor a pantalla completa
  // ---------------------------------------------------------------------------
  function editor(info, opts, cardBox) {
    const cat = { transiciones: info.transiciones || {}, filtros: info.filtros || {}, animaciones: info.animaciones || {},
      anim_texto: info.anim_texto || {}, stickers: info.stickers || {} };
    const lote = info.proyecto.lote;
    const KEY = "derReelBorrador:" + lote;
    let saved = clone(info.proyecto);
    let p = clone(info.proyecto);
    p.clips.forEach(c => { c.id = c.id || uid(); });
    let archivo = info.archivo, sel = -1, tool = null, trans = -1, PPS = 46, busy = false;
    let selT = -1, selS = -1;   // texto o sticker elegido
    const hist = [], fut = [];

    // borrador guardado en el celular (cambios sin exportar)
    const draft = JSON.parse(localStorage.getItem(KEY) || "null");
    let recuperado = false;
    if (draft && draft.p && draft.version === saved.version && JSON.stringify(draft.p) !== JSON.stringify(p)) {
      p = draft.p; recuperado = true;
    }
    p.textos = p.textos || []; p.stickers = p.stickers || [];

    const root = document.createElement("div");
    root.className = "rx";
    root.innerHTML = `
      <div class="rx-top">
        <button type="button" data-x="cerrar" class="rx-ghost" aria-label="Cerrar">✕</button>
        <button type="button" data-x="undo" class="rx-ghost" aria-label="Deshacer">↶</button>
        <button type="button" data-x="redo" class="rx-ghost" aria-label="Rehacer">↷</button>
        <span class="rx-sp"></span>
        <button type="button" data-x="previa" class="rx-sec">Vista previa</button>
        <button type="button" data-x="exportar" class="rx-prim">Exportar</button>
      </div>
      <div class="rx-stage">
        <video playsinline controls preload="metadata"></video>
        <div class="rx-ov" hidden></div>
        <div class="rx-badge"></div>
        <div class="rx-busy" hidden><div class="rx-bar"><i></i></div><p></p></div>
      </div>
      <div class="rx-meta"><b class="rx-total"></b><span class="rx-n"></span>
        <span class="rx-zoom"><button type="button" data-z="-1" aria-label="Alejar línea de tiempo">−</button><button type="button" data-z="1" aria-label="Acercar línea de tiempo">+</button></span></div>
      <div class="rx-tlw"><div class="rx-tl"></div><div class="rx-lanes"></div></div>
      <div class="rx-sheet" hidden><div class="rx-sheet-h"><b></b><button type="button" class="rx-ok">Listo</button></div><div class="rx-sheet-b"></div></div>
      <nav class="rx-tools"></nav>`;
    document.body.appendChild(root);
    document.body.classList.add("rx-abierto");
    const $ = s => root.querySelector(s);
    const video = $(".rx-stage video");
    video.src = archivo;
    $(".rx-badge").textContent = `Versión ${saved.version || 0}`;

    // --- historial y borrador ------------------------------------------------
    const snap = () => JSON.stringify(p);
    let last = snap();
    const keepDraft = () => localStorage.setItem(KEY, JSON.stringify({ version: saved.version, p, t: Date.now() }));
    function commit() {
      const s = snap();
      if (s === last) return paint();
      hist.push(last); if (hist.length > 60) hist.shift();
      fut.length = 0; last = s;
      keepDraft();
      paint();
      programarPrevia();
    }

    // --- vista previa automática: el video de arriba siempre muestra lo último que editaste ---
    let rendered = snap(), autoT = null, autoBusy = false, exported = snap();
    function estadoCambios() {
      const b = $(".rx-badge"), now = snap();
      if (autoBusy) { b.innerHTML = `<i class="rx-spin"></i>Actualizando la vista previa…`; b.classList.add("pend"); return; }
      if (now !== rendered) { b.textContent = "Cambios sin ver · se actualiza solo"; b.classList.add("pend"); return; }
      b.classList.remove("pend");
      b.textContent = now === exported ? `Versión ${saved.version || 0}` : "Vista previa · falta Exportar para descargar";
      $("[data-x=exportar]").classList.toggle("pulso", now !== exported);
    }
    function programarPrevia() {
      estadoCambios();
      clearTimeout(autoT);
      autoT = setTimeout(autoPrevia, 2500);
    }
    async function autoPrevia() {
      if (busy || autoBusy) { autoT = setTimeout(autoPrevia, 2000); return; }
      const want = snap();
      if (want === rendered) return estadoCambios();
      autoBusy = true; estadoCambios();
      try {
        const r = await fetch("/api/reel/editar", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lote, proyecto: JSON.parse(want), vista_previa: true }) });
        const j = await r.json();
        if (r.status === 409) { autoBusy = false; autoT = setTimeout(autoPrevia, 3000); return; }
        if (!r.ok) throw new Error(j.error);
        let st;
        do {
          await new Promise(ok => setTimeout(ok, 1200));
          try { st = await (await fetch("/api/trabajo/" + j.job)).json(); } catch (_) { st = { estado: "procesando" }; }
        } while (st.estado === "procesando");
        if (st.estado === "error") throw new Error(st.error);
        const t = video.currentTime || 0, playing = !video.paused;
        archivo = st.archivo; video.src = archivo; video.load();
        video.addEventListener("loadedmetadata", () => { video.currentTime = Math.min(t, video.duration - 0.05); if (playing) video.play().catch(() => {}); overlay(); }, { once: true });
        rendered = want;
      } catch (err) { toast("No se pudo actualizar la vista previa: " + String(err.message || err).slice(0, 200)); rendered = want; }
      finally {
        autoBusy = false; estadoCambios();
        if (snap() !== rendered) programarPrevia();
      }
    }
    function undo() { if (!hist.length) return; fut.push(last); last = hist.pop(); p = JSON.parse(last); afterHistory(); }
    function redo() { if (!fut.length) return; hist.push(last); last = fut.pop(); p = JSON.parse(last); afterHistory(); }
    function afterHistory() {
      keepDraft();
      programarPrevia();
      if (sel >= p.clips.length) sel = -1;
      if (trans >= p.clips.length - 1) trans = -1;
      p.textos = p.textos || []; p.stickers = p.stickers || [];
      if (selT >= p.textos.length) selT = -1;
      if (selS >= p.stickers.length) selS = -1;
      paint();
      if (tool && (sel >= 0 || !CLIP_TOOLS.has(tool))) openTool(tool); else closeTool();
      overlay();
    }

    // --- línea de tiempo -----------------------------------------------------
    function paint() {
      $(".rx-total").textContent = tc(total(p));
      $(".rx-n").textContent = `${p.clips.length} clip${p.clips.length > 1 ? "s" : ""} · ${FORMATOS[p.opciones.formato || "historia"]}`;
      $("[data-x=undo]").disabled = busy || !hist.length;
      $("[data-x=redo]").disabled = busy || !fut.length;
      const tl = $(".rx-tl");
      tl.innerHTML = p.clips.map((c, i) => {
        const w = Math.max(44, dur(c) * PPS);
        const full = c.source_duration / c.speed * PPS;
        const off = c.start / c.speed * PPS;
        const badges = [c.speed !== 1 && c.kind === "video" ? `${String(c.speed).replace(".", ",")}x` : "",
          c.reverse ? "⇄" : "", c.kind === "video" && !c.mute ? "♪" : "", c.filtro && c.filtro !== "ninguno" ? "◐" : ""].filter(Boolean).join(" ");
        return `<div class="rx-clip${i === sel ? " on" : ""}" data-i="${i}" style="width:${w}px;background-image:url('${c.tira}');
            background-size:${c.kind === "foto" ? "auto 100%" : full + "px 100%"};background-position:${c.kind === "foto" ? 0 : -off}px 0">
            <span class="rx-look-l" style="backdrop-filter:${cssLook(c)};-webkit-backdrop-filter:${cssLook(c)}"></span>
            <span class="rx-d">${fmt(dur(c))}s</span>${badges ? `<span class="rx-bd">${badges}</span>` : ""}
            ${i === sel ? `<i class="rx-h l" data-h="l"></i><i class="rx-h r" data-h="r"></i>` : ""}
          </div>${i < p.clips.length - 1 ? `<button type="button" class="rx-tr${trans === i ? " on" : ""}${c.transition === "none" ? " seco" : ""}" data-t="${i}" aria-label="Transición entre ${i + 1} y ${i + 2}">${c.transition === "none" ? "" : "⋈"}</button>` : ""}`;
      }).join("") + `<button type="button" class="rx-add" aria-label="Agregar clips">+</button>`;
      tl.querySelectorAll(".rx-clip").forEach(el => {
        el.onclick = e => { if (e.target.dataset.h || el.dataset.moved) return; select(+el.dataset.i === sel ? -1 : +el.dataset.i); };
        dragReorder(el);
      });
      tl.querySelectorAll(".rx-tr").forEach(b => b.onclick = () => { sel = -1; trans = +b.dataset.t; paint(); openTool("transicion"); });
      tl.querySelector(".rx-add").onclick = () => addClips();
      tl.querySelectorAll(".rx-h").forEach(h => trimHandle(h));
      lanes();
      overlay();
      tools();
    }

    // posición en píxeles de un segundo del reel (los clips tienen ancho mínimo y entre ellos va la transición)
    function timeMap() {
      const marks = [];
      let t = 0, x = 16;
      p.clips.forEach((c, i) => {
        const d = dur(c), w = Math.max(44, d * PPS);
        marks.push({ t0: t, t1: t + d, x0: x, x1: x + w });
        let T = 0;
        if (i < p.clips.length - 1 && c.transition !== "none") T = Math.min(c.transition_seconds, d / 2, dur(p.clips[i + 1]) / 2);
        t += d - T; x += w + (i < p.clips.length - 1 ? 28 : 0);
      });
      const end = total(p);
      marks.push({ t0: t, t1: end, x0: x, x1: x + (end - t) * PPS });
      return marks;
    }
    function tx(t, m = timeMap()) {
      for (const k of m) if (t <= k.t1) return k.x0 + (Math.max(t, k.t0) - k.t0) / Math.max(0.001, k.t1 - k.t0) * (k.x1 - k.x0);
      const k = m[m.length - 1]; return k.x1;
    }
    function xt(x, m = timeMap()) {
      for (const k of m) if (x <= k.x1) return k.t0 + (Math.max(x, k.x0) - k.x0) / Math.max(1, k.x1 - k.x0) * (k.t1 - k.t0);
      return total(p);
    }

    function lanes() {
      const m = timeMap(), box = $(".rx-lanes");
      const bar = (it, i, kind) => {
        const a = tx(it.inicio, m), b = Math.max(a + 30, tx(it.fin, m));
        const on = (kind === "t" ? selT : selS) === i;
        const label = kind === "t" ? (it.texto || "Texto").replace(/\*/g, "").slice(0, 40) : (cat.stickers[it.tipo] || it.tipo);
        return `<div class="rx-bar-${kind}${on ? " on" : ""}" data-${kind}="${i}" style="left:${a}px;width:${b - a}px">
          <span>${esc(label)}</span>${on ? `<i class="rx-h l" data-bh="l"></i><i class="rx-h r" data-bh="r"></i>` : ""}</div>`;
      };
      const w = tx(total(p), m) + 60;
      box.style.width = w + "px";
      // renglones: lo que se superpone en el tiempo va en otro renglón (como las pistas de CapCut)
      const pack = (list, kind) => {
        const rows = [];
        list.forEach((it, i) => {
          let r = rows.findIndex(row => row.every(j => list[j].fin <= it.inicio + 0.01 || list[j].inicio >= it.fin - 0.01));
          if (r < 0) { rows.push([]); r = rows.length - 1; }
          rows[r].push(i);
        });
        return rows.map(row => `<div class="rx-lane">${row.map(i => bar(list[i], i, kind)).join("")}</div>`).join("");
      };
      box.innerHTML = pack(p.textos, "t") + pack(p.stickers, "s");
      box.querySelectorAll("[data-t],[data-s]").forEach(el => barDrag(el));
    }

    // arrastrar una barra de texto/sticker: mover en el tiempo o estirar desde los bordes
    function barDrag(el) {
      const kind = el.dataset.t !== undefined ? "t" : "s", i = +(el.dataset.t ?? el.dataset.s);
      const list = kind === "t" ? p.textos : p.stickers;
      el.onpointerdown = e => {
        const it = list[i], x0 = e.clientX, a0 = it.inicio, b0 = it.fin, side = e.target.dataset.bh;
        let moved = false;
        el.setPointerCapture(e.pointerId);
        el.onpointermove = ev => {
          const dt = (ev.clientX - x0) / PPS;
          if (Math.abs(ev.clientX - x0) > 4) moved = true;
          if (!moved) return;
          const T = total(p);
          if (side === "l") it.inicio = Math.min(Math.max(0, a0 + dt), it.fin - 0.3);
          else if (side === "r") it.fin = Math.max(Math.min(T, b0 + dt), it.inicio + 0.3);
          else { const len = b0 - a0; it.inicio = Math.min(Math.max(0, a0 + dt), Math.max(0, T - len)); it.fin = it.inicio + len; }
          const m = timeMap(), a = tx(it.inicio, m);
          el.style.left = a + "px"; el.style.width = Math.max(30, tx(it.fin, m) - a) + "px";
        };
        el.onpointerup = () => {
          el.onpointermove = el.onpointerup = null;
          if (moved) { commit(); if (tool) openTool(tool); }
          else selectLayer(kind, i);
        };
      };
    }

    function selectLayer(kind, i) {
      sel = -1; trans = -1;
      selT = kind === "t" ? i : -1; selS = kind === "s" ? i : -1;
      paint(); openTool(kind === "t" ? "texto-ed" : "sticker-ed");
      const it = (kind === "t" ? p.textos : p.stickers)[i];
      if (it && video.duration) { video.pause(); video.currentTime = Math.min(video.duration - 0.05, it.inicio + 0.4); }
    }

    // capa sobre el video: muestra el texto/sticker elegido y se mueve arrastrando
    function overlay() {
      const ov = $(".rx-ov");
      const it = selT >= 0 ? p.textos[selT] : selS >= 0 ? p.stickers[selS] : null;
      if (!it || !video.videoWidth) { ov.hidden = true; return; }
      const st = $(".rx-stage").getBoundingClientRect(), vr = video.getBoundingClientRect();
      const k = Math.min(vr.width / video.videoWidth, vr.height / video.videoHeight);
      const w = video.videoWidth * k, h = video.videoHeight * k;
      const left = vr.left - st.left + (vr.width - w) / 2, top = vr.top - st.top + (vr.height - h) / 2;
      Object.assign(ov.style, { left: left + "px", top: top + "px", width: w + "px", height: h + "px" });
      ov.hidden = false;
      const s = w / 1080;
      let inner;
      if (selT >= 0) {
        const fam = { title: "DER Titulo", subtitle: "DER Sub", body: "DER Cuerpo" }[it.rol] || "DER Sub";
        const hl = (it.color || "").toLowerCase() === BRAND.naranja ? "#fff" : BRAND.naranja;
        const html = esc(it.texto || "Texto").replace(/\*([^*]+)\*/g, `<b style="color:${hl};font-weight:inherit">$1</b>`).replace(/\n/g, "<br>");
        inner = `<div class="rx-ov-it" style="left:${it.x * 100}%;top:${it.y * 100}%;font-family:'${fam}';font-size:${it.tamano * s}px;color:${it.color};
          text-align:${{ izquierda: "left", centro: "center", derecha: "right" }[it.alinear] || "center"};${it.caja ? `background:${it.caja};padding:${it.tamano * s * .28}px ${it.tamano * s * .45}px;border-radius:${it.tamano * s * .18}px;` : "text-shadow:0 2px 4px rgba(0,0,0,.6);"}
          ${it.mayus || it.rol === "title" ? "text-transform:uppercase;" : ""}max-width:84%">${html}</div>`;
      } else {
        const label = cat.stickers[it.tipo] || it.tipo;
        const size = it.tipo === "marco" ? "inset:6%;left:50%;top:50%;width:88%;height:88%" : `width:${(it.tipo === "logo" ? 260 : 160) * it.tamano * s}px;height:${(it.tipo === "logo" ? 120 : 70) * it.tamano * s}px`;
        inner = `<div class="rx-ov-it rx-ov-st" style="left:${it.x * 100}%;top:${it.y * 100}%;${size}"><span>${esc(label)}</span></div>`;
      }
      ov.innerHTML = inner + `<p class="rx-ov-tip">Arrastralo para ubicarlo</p>`;
      const el = ov.querySelector(".rx-ov-it");
      el.onpointerdown = e => {
        e.preventDefault(); el.setPointerCapture(e.pointerId);
        const r = ov.getBoundingClientRect();
        el.onpointermove = ev => {
          it.x = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
          it.y = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
          el.style.left = it.x * 100 + "%"; el.style.top = it.y * 100 + "%";
        };
        el.onpointerup = () => { el.onpointermove = el.onpointerup = null; commit(); };
      };
    }
    video.addEventListener("loadedmetadata", () => overlay());
    window.addEventListener("resize", () => overlay());

    function select(i) {
      selT = selS = -1;
      sel = i; trans = -1;
      if (i >= 0 && tool && CLIP_TOOLS.has(tool)) openTool(tool); else closeTool();
      paint();
      if (i >= 0) $(`.rx-clip[data-i="${i}"]`)?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    }

    // arrastrar los bordes del clip seleccionado para recortar (como CapCut)
    function trimHandle(h) {
      h.onpointerdown = e => {
        e.preventDefault(); e.stopPropagation();
        const c = p.clips[sel], x0 = e.clientX, s0 = c.start, e0 = c.end, side = h.dataset.h;
        h.setPointerCapture(e.pointerId);
        const el = h.parentElement;
        h.onpointermove = ev => {
          const dt = (ev.clientX - x0) / PPS * (c.kind === "foto" ? 1 : c.speed);
          if (c.kind === "foto") {
            c.end = Math.min(MAX_FOTO, Math.max(0.5, side === "r" ? e0 + dt : e0 - dt));
            c.start = 0; c.source_duration = c.end;
          } else if (side === "l") c.start = Math.min(Math.max(0, s0 + dt), c.end - MIN * c.speed);
          else c.end = Math.max(Math.min(c.source_duration, e0 + dt), c.start + MIN * c.speed);
          el.style.width = Math.max(44, dur(c) * PPS) + "px";
          if (c.kind === "video") el.style.backgroundPosition = `${-c.start / c.speed * PPS}px 0`;
          el.querySelector(".rx-d").textContent = fmt(dur(c)) + "s";
          $(".rx-total").textContent = tc(total(p));
        };
        h.onpointerup = () => { h.onpointermove = h.onpointerup = null; commit(); if (tool) openTool(tool); };
      };
    }

    // mantener apretado un clip y arrastrarlo para cambiarlo de lugar
    function dragReorder(el) {
      let timer = null;
      el.addEventListener("pointerdown", e => {
        if (e.target.dataset.h) return;
        const i = +el.dataset.i, x0 = e.clientX;
        delete el.dataset.moved;
        timer = setTimeout(() => {
          el.classList.add("drag"); el.setPointerCapture(e.pointerId); el.dataset.moved = "1";
          const blocks = [...root.querySelectorAll(".rx-clip")];
          const move = ev => { el.style.transform = `translateX(${ev.clientX - x0}px)`; };
          const up = ev => {
            el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up);
            el.classList.remove("drag"); el.style.transform = "";
            const x = ev.clientX;
            let to = blocks.findIndex(b => { const r = b.getBoundingClientRect(); return x < r.left + r.width / 2; });
            if (to < 0) to = blocks.length;
            if (to > i) to--;
            if (to !== i) { const [c] = p.clips.splice(i, 1); p.clips.splice(to, 0, c); sel = to; commit(); toast("Clip movido."); }
            setTimeout(() => { delete el.dataset.moved; }, 50);
          };
          el.addEventListener("pointermove", move); el.addEventListener("pointerup", up);
        }, 420);
      });
      const cancel = () => clearTimeout(timer);
      el.addEventListener("pointerup", cancel); el.addEventListener("pointercancel", cancel);
      el.addEventListener("pointermove", e => { if (Math.abs(e.movementX) > 4 && !el.classList.contains("drag")) cancel(); });
    }

    // --- barra de herramientas -------------------------------------------------
    const CLIP_TOOLS = new Set(["recortar", "dividir", "velocidad", "duracion", "volumen", "encuadre", "filtros", "ajustes",
      "animacion", "girar", "congelar", "mover"]);
    function tools() {
      const c = p.clips[sel];
      const items = c ? [
        ["recortar", "cortar", "Recortar"], ["dividir", "dividir", "Dividir"],
        ...(c.kind === "video" ? [["velocidad", "velocidad", "Velocidad"], ["volumen", "volumen", "Volumen"]] : [["duracion", "velocidad", "Duración"]]),
        ["encuadre", "encuadre", "Encuadre"], ["filtros", "filtro", "Filtros"], ["ajustes", "ajustes", "Ajustes"],
        ["animacion", "anim", "Animación"], ["girar", "girar", "Girar"],
        ...(c.kind === "video" ? [["congelar", "congelar", "Congelar"], ["invertir", "invertir", c.reverse ? "Al derecho" : "Invertir"]] : []),
        ["duplicar", "duplicar", "Duplicar"], ["mover", "mover", "Mover"], ["borrar", "borrar", "Borrar"],
      ] : [
        ["agregar", "agregar", "Agregar"], ["formato", "formato", "Formato"], ["musica", "musica", "Música"],
        ["textos", "texto", "Texto"], ["stickers", "logo", "Stickers"], ["ritmo", "velocidad", "Al ritmo"],
        ["voz", "voz", "Voz en off"], ["titulo", "texto", "Título"], ["marca", "logo", "Logo y cierre"],
        ["todo", "filtro", "Filtro a todo"], ["guardar-plantilla", "duplicar", "Guardar como plantilla"],
      ];
      if (selT >= 0 || selS >= 0) {
        const nav = $(".rx-tools");
        nav.innerHTML = `<div class="rx-tools-h">${selT >= 0 ? "Texto" : "Sticker"} elegido <button type="button" class="rx-desel">Deseleccionar</button></div>
          <div class="rx-tools-r"><button type="button" data-lay="dup">${ico("duplicar")}<span>Duplicar</span></button>
          <button type="button" data-lay="todo">${ico("formato")}<span>Todo el reel</span></button>
          <button type="button" data-lay="del" class="rx-danger">${ico("borrar")}<span>Borrar</span></button></div>`;
        nav.querySelector(".rx-desel").onclick = () => { selT = selS = -1; closeTool(); paint(); };
        nav.querySelectorAll("[data-lay]").forEach(b => b.onclick = () => layerAction(b.dataset.lay));
        return;
      }
      const nav = $(".rx-tools");
      nav.innerHTML = (c ? `<div class="rx-tools-h">Clip ${sel + 1} · ${c.kind === "foto" ? "foto" : "video"} <button type="button" class="rx-desel">Deseleccionar</button></div>` : `<div class="rx-tools-h">Tocá un clip para editarlo · o editá todo el reel</div>`) +
        `<div class="rx-tools-r">${items.map(([k, ic, n]) => `<button type="button" data-tool="${k}" class="${tool === k ? "on" : ""}${k === "borrar" ? " rx-danger" : ""}">${ico(ic)}<span>${n}</span></button>`).join("")}</div>`;
      nav.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => action(b.dataset.tool));
      const ds = nav.querySelector(".rx-desel");
      if (ds) ds.onclick = () => select(-1);
    }

    function layerAction(a) {
      const list = selT >= 0 ? p.textos : p.stickers, i = selT >= 0 ? selT : selS;
      if (a === "dup") { list.splice(i + 1, 0, { ...clone(list[i]), id: uid(), y: Math.min(0.95, list[i].y + 0.06) }); if (selT >= 0) selT++; else selS++; toast("Duplicado."); }
      if (a === "todo") { list[i].inicio = 0; list[i].fin = total(p); toast("Ahora dura todo el reel."); }
      if (a === "del") { list.splice(i, 1); selT = selS = -1; closeTool(); toast("Borrado (↶ para deshacer)."); }
      commit(); if (selT >= 0 || selS >= 0) openTool(selT >= 0 ? "texto-ed" : "sticker-ed");
    }

    function addText(preset) {
      const T = total(p), now = Math.min(Math.max(0, video.currentTime || 0), Math.max(0, T - 1));
      const base = { id: uid(), texto: "Escribí acá", inicio: now, fin: Math.min(T, now + 3), x: 0.5, y: 0.5, tamano: 64, rol: "subtitle",
        color: BRAND.blanco, caja: "", alinear: "centro", anim: "aparecer", mayus: false, sombra: true };
      const P = {
        titulo: { texto: "Título *grande*", rol: "title", tamano: 96, y: 0.42, anim: "subir" },
        subtitulo: { texto: "Subtítulo", rol: "subtitle", tamano: 56, y: 0.55 },
        etiqueta: { texto: "Asunción · 2026", rol: "subtitle", tamano: 44, y: 0.18, caja: BRAND.naranja, anim: "deslizar" },
        cta: { texto: "Escribinos · somosder.ar", rol: "subtitle", tamano: 50, y: 0.82, caja: BRAND.oscuro, anim: "golpe" },
        texto: { texto: "Texto corto", rol: "body", tamano: 48, y: 0.7 },
        escribir: { texto: "Así se hace un evento", rol: "subtitle", tamano: 64, y: 0.5, anim: "escribir" },
      }[preset] || {};
      p.textos.push({ ...base, ...P });
      selT = p.textos.length - 1; selS = -1; sel = -1;
      commit(); openTool("texto-ed");
      setTimeout(() => body.querySelector("textarea")?.select(), 50);
    }

    function addSticker(tipo) {
      const T = total(p);
      const pos = { logo: [0.82, 0.1], marco: [0.5, 0.5], puntos: [0.85, 0.85], barra: [0.15, 0.3], web: [0.5, 0.9], flecha: [0.5, 0.6] }[tipo] || [0.5, 0.5];
      p.stickers.push({ id: uid(), tipo, inicio: 0, fin: T, x: pos[0], y: pos[1], tamano: 1, color: BRAND.naranja, opacidad: 1, giro: 0,
        variante: "on_dark", logo: "", anim: "aparecer" });
      selS = p.stickers.length - 1; selT = -1; sel = -1;
      commit(); openTool("sticker-ed");
    }

    // cortar al ritmo: cada clip dura N tiempos de la música (cortes secos, como los "beat sync" de CapCut)
    async function alRitmo(nBeats, keepTransitions) {
      toast("Buscando el ritmo de la música…");
      try {
        const r = await fetch("/api/reel/ritmo", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ music: p.opciones.music, music_start: p.opciones.music_start || 0 }) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error);
        const beat = 60 / j.bpm, step = beat * nBeats;
        let cortos = 0;
        p.clips.forEach((c, i) => {
          const T = keepTransitions && i < p.clips.length - 1 && c.transition !== "none" ? c.transition_seconds : 0;
          const want = step + T + (i === 0 ? j.primero : 0);
          if (!keepTransitions) c.transition = "none";
          if (c.kind === "foto") { c.start = 0; c.end = c.source_duration = +want.toFixed(3); return; }
          const room = (c.source_duration - c.start) / c.speed;
          if (room < want) { cortos++; c.end = c.source_duration; return; }
          c.end = +(c.start + want * c.speed).toFixed(3);
        });
        commit();
        toast(`Listo: ${Math.round(j.bpm)} BPM, un corte cada ${fmt(step)} s.${cortos ? ` ${cortos} clip(s) eran más cortos y quedaron enteros.` : ""}`);
      } catch (err) { toast("No se pudo: " + err.message); }
    }

    function action(k) {
      const c = p.clips[sel];
      if (k === "agregar") return addClips();
      if (k === "guardar-plantilla") return guardarPlantilla();
      if (k === "duplicar") { p.clips.splice(sel + 1, 0, { ...clone(c), id: uid() }); sel++; toast("Clip duplicado."); return commit(); }
      if (k === "borrar") {
        if (p.clips.length === 1) return toast("El reel tiene que tener al menos un clip.");
        p.clips.splice(sel, 1); sel = -1; closeTool(); toast("Clip borrado (↶ para deshacer)."); return commit();
      }
      if (k === "invertir") {
        if (!c.reverse && dur(c) > MAX_REV) return toast(`Para invertir, el clip tiene que durar ${MAX_REV} s o menos. Recortalo primero.`);
        c.reverse = !c.reverse; toast(c.reverse ? "El clip va al revés." : "El clip vuelve al derecho."); return commit();
      }
      if (tool === k) return closeTool();
      openTool(k);
    }

    // --- paneles ---------------------------------------------------------------
    const sheet = $(".rx-sheet"), body = $(".rx-sheet-b");
    $(".rx-ok").onclick = () => closeTool();
    function closeTool() {
      tool = null; sheet.hidden = true; root.classList.remove("con-panel");
      if (trans >= 0) { trans = -1; paint(); } else { tools(); overlay(); }
    }
    const range = (k, label, min, max, step, val, suf = "") => `<label class="rx-r"><span>${label}<output>${fmt(val)}${suf}</output></span>
      <input type="range" data-k="${k}" data-suf="${suf}" min="${min}" max="${max}" step="${step}" value="${val}"></label>`;
    const chips = (k, items, val) => `<div class="rx-chips">${(Array.isArray(items) ? items : Object.entries(items)).map(([v, n]) =>
      `<button type="button" data-k="${k}" data-v="${v}" class="${String(val) === String(v) ? "on" : ""}">${esc(n)}</button>`).join("")}</div>`;
    const TITLES = { recortar: "Recortar", dividir: "Dividir", velocidad: "Velocidad", duracion: "Duración de la foto", volumen: "Volumen",
      encuadre: "Encuadre", filtros: "Filtros", ajustes: "Ajustes", animacion: "Animación", girar: "Girar y espejar",
      congelar: "Congelar imagen", mover: "Mover", transicion: "Transición", formato: "Formato", musica: "Música",
      voz: "Voz en off", titulo: "Título de apertura", marca: "Logo y cierre", todo: "Filtro para todos los clips",
      textos: "Texto", stickers: "Stickers", ritmo: "Cortar al ritmo", "texto-ed": "Editar texto", "sticker-ed": "Editar sticker" };

    function openTool(k) {
      if (CLIP_TOOLS.has(k) && sel < 0) return closeTool();
      if (k === "transicion" && trans < 0) return closeTool();
      if (k === "texto-ed" && selT < 0) return closeTool();
      if (k === "sticker-ed" && selS < 0) return closeTool();
      tool = k; sheet.hidden = false; root.classList.add("con-panel");
      const c = p.clips[sel];
      $(".rx-sheet-h b").textContent = TITLES[k] || "";
      body.innerHTML = panelHTML(k, c);
      bindPanel(k, c);
      tools();
    }

    function scrubHTML(c, loop) {
      return `<div class="rx-scrub"><video muted playsinline preload="auto" src="${c.vista || ""}"></video>
        ${loop ? `<p class="rx-hint">Se repite el tramo elegido. Tocá el video para pausar.</p>` :
        `<input type="range" class="rx-pos" min="${c.start}" max="${c.end}" step="0.05" value="${((c.start + c.end) / 2).toFixed(2)}">
        <p class="rx-hint">Mové la barra hasta el cuadro exacto. <b class="rx-at"></b></p>`}</div>`;
    }

    function panelHTML(k, c) {
      const o = p.opciones;
      switch (k) {
        case "recortar":
          if (c.kind === "foto") return range("dur", "Duración", 0.5, MAX_FOTO, 0.5, c.end, " s");
          return scrubHTML(c, true) + range("start", "Inicio", 0, c.source_duration, 0.05, c.start, " s") +
            range("end", "Fin", 0, c.source_duration, 0.05, c.end, " s") + `<p class="rx-hint">También podés arrastrar los bordes blancos del clip en la línea de tiempo.</p>`;
        case "dividir":
          if (c.kind === "foto") return range("split", "Dividir en el segundo", 0.3, Math.max(0.4, c.end - 0.3), 0.1, +(c.end / 2).toFixed(1), " s") + `<button type="button" class="rx-btn" data-a="split">Dividir acá</button>`;
          return scrubHTML(c) + `<button type="button" class="rx-btn" data-a="split">Dividir acá</button>`;
        case "congelar":
          return scrubHTML(c) + `<button type="button" class="rx-btn" data-a="freeze">Congelar este cuadro (2 s)</button>`;
        case "velocidad":
          return chips("speed", [["0.25", "0,25x"], ["0.5", "0,5x"], ["0.75", "0,75x"], ["1", "1x"], ["1.5", "1,5x"], ["2", "2x"], ["3", "3x"], ["4", "4x"]], c.speed) +
            range("speed", "Velocidad", 0.25, 4, 0.05, c.speed, "x") + `<p class="rx-hint">Más lento = el clip dura más. El sonido original acompaña la velocidad.</p>`;
        case "duracion":
          return range("dur", "Duración", 0.5, MAX_FOTO, 0.5, c.end, " s");
        case "volumen":
          return `<label class="rx-sw"><input type="checkbox" data-k="sound" ${c.mute ? "" : "checked"}><span>Sonido original del clip</span></label>` +
            range("volume", "Volumen", 0, 2, 0.05, c.volume, "") + `<p class="rx-hint">1,0 = volumen original · 2,0 = el doble. Con sonido original, la música baja sola.</p>`;
        case "encuadre":
          return chips("fit", { llenar: "Llenar (recorta)", ajustar: "Ajustar (entra entero)" }, c.fit) +
            (c.fit === "ajustar" ? `<div class="rx-sub">Fondo</div><div class="rx-sw-row">
              <button type="button" data-k="fondo" data-v="blur" class="rx-blur ${c.fondo === "blur" ? "on" : ""}">Desenfocado</button>
              ${Object.entries(BRAND).map(([n, v]) => `<button type="button" data-k="fondo" data-v="${v}" title="${n}" aria-label="Fondo ${n}" class="rx-dot ${c.fondo === v ? "on" : ""}" style="background:${v}"></button>`).join("")}
              <label class="rx-dot rx-pick" title="Otro color"><input type="color" data-k="fondo-pick" value="${/^#/.test(c.fondo) ? c.fondo : "#333333"}"></label></div>` : "") +
            range("zoom", "Zoom", 1, 3, 0.05, c.zoom, "x") + range("pan_x", "Mover ← →", -1, 1, 0.05, c.pan_x) +
            range("pan_y", "Mover ↑ ↓", -1, 1, 0.05, c.pan_y) + `<button type="button" class="rx-btn sec" data-a="centrar">Centrar</button>`;
        case "filtros":
          return `<div class="rx-fl">${Object.entries(cat.filtros).map(([v, n]) => `<button type="button" data-k="filtro" data-v="${v}" class="${c.filtro === v ? "on" : ""}">
            <img src="${c.miniatura}" alt="" style="filter:${CSS_FILTRO[v] || "none"}"><span>${esc(n)}</span></button>`).join("")}</div>
            <button type="button" class="rx-btn sec" data-a="filtro-todos">Usar este filtro en todos los clips</button>`;
        case "todo":
          return `<div class="rx-fl">${Object.entries(cat.filtros).map(([v, n]) => `<button type="button" data-k="filtro-global" data-v="${v}">
            <img src="${p.clips[0].miniatura}" alt="" style="filter:${CSS_FILTRO[v] || "none"}"><span>${esc(n)}</span></button>`).join("")}</div>`;
        case "ajustes":
          return `<div class="rx-look"><img src="${c.miniatura}" alt="" style="filter:${cssLook(c)}"></div>` +
            range("brillo", "Brillo", -100, 100, 1, c.brillo) + range("contraste", "Contraste", -100, 100, 1, c.contraste) +
            range("saturacion", "Saturación", -100, 100, 1, c.saturacion) + range("temperatura", "Temperatura", -100, 100, 1, c.temperatura) +
            range("vineta", "Viñeta", 0, 100, 1, c.vineta) + `<button type="button" class="rx-btn sec" data-a="reset-ajustes">Restablecer</button>`;
        case "animacion":
          return chips("anim", cat.animaciones, c.anim) + `<p class="rx-hint">Se ve en la vista previa. "Paneo lento" queda muy bien en fotos.</p>`;
        case "girar":
          return `<div class="rx-grid4"><button type="button" class="rx-btn sec" data-a="rot-l">⟲ 90°</button><button type="button" class="rx-btn sec" data-a="rot-r">⟳ 90°</button>
            <button type="button" class="rx-btn sec ${c.flip_h ? "on" : ""}" data-a="flip-h">Espejo ⇆</button><button type="button" class="rx-btn sec ${c.flip_v ? "on" : ""}" data-a="flip-v">Espejo ⇅</button></div>
            <p class="rx-hint">Girado: ${c.rotate || 0}°</p>`;
        case "mover":
          return `<div class="rx-grid4"><button type="button" class="rx-btn sec" data-a="izq" ${sel === 0 ? "disabled" : ""}>← Antes</button>
            <button type="button" class="rx-btn sec" data-a="der" ${sel === p.clips.length - 1 ? "disabled" : ""}>Después →</button></div>
            <p class="rx-hint">También: mantené apretado un clip en la línea de tiempo y arrastralo.</p>`;
        case "transicion": {
          const t = p.clips[trans];
          return chips("transition", cat.transiciones, t.transition) + (t.transition === "none" ? "" :
            range("transition_seconds", "Duración", 0.2, 1.5, 0.1, t.transition_seconds, " s")) +
            `<button type="button" class="rx-btn sec" data-a="trans-todas">Usar en todos los cortes</button>`;
        }
        case "formato":
          return chips("formato", { historia: "9:16 · Reel / historia", post: "4:5 · Post", cuadrado: "1:1 · Cuadrado" }, o.formato || "historia") +
            `<p class="rx-hint">Cambia el tamaño de todo el reel. Revisá el encuadre de cada clip en la vista previa.</p>`;
        case "musica": {
          const propia = o.music && !o.music.startsWith("auto") && o.music !== "none";
          return `<select data-k="music" class="rx-sel">${(opts.musicas || []).map(([v, n]) => `<option value="${esc(v)}" ${v === o.music ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>` +
            range("music_volume", "Volumen de la música", 0, 1.5, 0.05, o.music_volume ?? 0.9) +
            (propia ? range("music_start", "Empieza en el segundo", 0, 180, 1, o.music_start || 0, " s") : "") +
            range("music_fade_out", "Fundido al final", 0, 6, 0.1, o.music_fade_out ?? 1.8, " s") +
            (o.music && o.music.startsWith("auto") ? `<button type="button" class="rx-btn sec" data-a="otra-cancion">Otra canción (misma onda)</button>` : "");
        }
        case "voz":
          return `<div class="rx-rec"><button type="button" class="rx-recb" data-a="grabar"><i></i><span>Grabar</span></button><b class="rx-rect">00:00</b></div>
            ${o.voz ? `<audio controls src="${p.voz_url || ""}"></audio>` : `<p class="rx-hint">Grabá con el micrófono del celular o subí un audio. Arranca junto con el reel.</p>`}
            <label class="rx-btn sec rx-file">Subir un audio<input type="file" accept="audio/*" hidden data-a="voz-archivo"></label>` +
            (o.voz ? range("voz_volume", "Volumen de la voz", 0, 2, 0.05, o.voz_volume ?? 1) +
              `<label class="rx-sw"><input type="checkbox" data-k="voz_ducking" ${o.voz_ducking !== false ? "checked" : ""}><span>Bajar la música cuando hablo</span></label>
              <button type="button" class="rx-btn sec rx-danger" data-a="quitar-voz">Quitar la voz</button>` : "");
        case "textos":
          return `<div class="rx-presets">${[["titulo", "Título grande"], ["subtitulo", "Subtítulo"], ["etiqueta", "Etiqueta con caja"],
            ["cta", "Llamado a la acción"], ["texto", "Texto corto"], ["escribir", "Máquina de escribir"]].map(([k2, n]) =>
            `<button type="button" data-a="add-text" data-v="${k2}" class="rx-preset rx-p-${k2}"><b>${n}</b></button>`).join("")}</div>
            ${p.textos.length ? `<div class="rx-sub">En este reel</div>${p.textos.map((t, i) => `<button type="button" class="rx-li" data-a="pick-text" data-v="${i}">
              <span>${esc((t.texto || "").replace(/\*/g, "").slice(0, 40))}</span><small>${fmt(t.inicio)}–${fmt(t.fin)} s</small></button>`).join("")}` : ""}
            <p class="rx-hint">Aparece donde está el video en pausa. Después lo movés arrastrando sobre el video y en la pista de abajo.</p>`;
        case "texto-ed": {
          const t = p.textos[selT], T = total(p);
          return `<textarea class="rx-ta" data-tk="texto" rows="2" placeholder="Escribí el texto">${esc(t.texto)}</textarea>
            <p class="rx-hint">*Entre asteriscos* va resaltado. Enter = renglón nuevo.</p>
            <div class="rx-chips">${[["0.14", "Arriba"], ["0.5", "Centro"], ["0.82", "Abajo"]].map(([v, n]) => `<button type="button" data-tpos="${v}">${n}</button>`).join("")}</div>` +
            range("t-tamano", "Tamaño", 16, 200, 1, t.tamano) +
            chips("t-rol", [["title", "Netron"], ["subtitle", "Subtítulo"], ["body", "Jost"]], t.rol) +
            `<div class="rx-sub">Color</div><div class="rx-sw-row">${Object.entries(BRAND).map(([n, v]) => `<button type="button" data-tcol="${v}" aria-label="${n}" class="rx-dot ${t.color === v ? "on" : ""}" style="background:${v}"></button>`).join("")}</div>
            <div class="rx-sub">Caja de fondo</div><div class="rx-sw-row"><button type="button" data-tbox="" class="rx-blur ${!t.caja ? "on" : ""}">Sin caja</button>
              ${Object.entries(BRAND).map(([n, v]) => `<button type="button" data-tbox="${v}" aria-label="caja ${n}" class="rx-dot ${t.caja === v ? "on" : ""}" style="background:${v}"></button>`).join("")}</div>` +
            chips("t-alinear", [["izquierda", "Izquierda"], ["centro", "Centro"], ["derecha", "Derecha"]], t.alinear) +
            `<div class="rx-sub">Animación</div>` + chips("t-anim", cat.anim_texto, t.anim) +
            range("t-inicio", "Aparece en", 0, Math.max(0.5, T - 0.3), 0.1, t.inicio, " s") + range("t-fin", "Se va en", 0.3, T, 0.1, t.fin, " s") +
            `<label class="rx-sw"><input type="checkbox" data-tchk="mayus" ${t.mayus ? "checked" : ""}><span>Mayúsculas</span></label>
             <label class="rx-sw"><input type="checkbox" data-tchk="sombra" ${t.sombra !== false ? "checked" : ""}><span>Sombra (sin caja)</span></label>`;
        }
        case "stickers":
          return `<div class="rx-presets">${Object.entries(cat.stickers).map(([k2, n]) => `<button type="button" data-a="add-sticker" data-v="${k2}" class="rx-preset"><b>${esc(n)}</b></button>`).join("")}</div>
            <p class="rx-hint">Se agrega para todo el reel. Lo ubicás arrastrando sobre el video y acortás su tiempo en la pista.</p>`;
        case "sticker-ed": {
          const st = p.stickers[selS], T = total(p);
          return `<p class="rx-hint"><b>${esc(cat.stickers[st.tipo] || st.tipo)}</b></p>` +
            range("s-tamano", "Tamaño", 0.2, 3, 0.05, st.tamano, "x") +
            (st.tipo === "logo" ? chips("s-variante", [["on_dark", "Para fondo oscuro"], ["on_light", "Para fondo claro"], ["on_orange", "Para naranja"]], st.variante) +
              `<select class="rx-sel" data-sk="logo"><option value="">Logo DER</option>${(opts.logos || []).map(n => `<option value="${esc(n)}" ${st.logo === n ? "selected" : ""}>${esc(n.replace(/\.(png|webp)$/i, ""))}</option>`).join("")}</select>`
              : `<div class="rx-sub">Color</div><div class="rx-sw-row">${Object.entries(BRAND).map(([n, v]) => `<button type="button" data-scol="${v}" aria-label="${n}" class="rx-dot ${st.color === v ? "on" : ""}" style="background:${v}"></button>`).join("")}</div>`) +
            (st.tipo === "flecha" ? range("s-giro", "Giro", -180, 180, 5, st.giro, "°") : "") +
            range("s-opacidad", "Opacidad", 0.1, 1, 0.05, st.opacidad) +
            `<div class="rx-sub">Animación</div>` + chips("s-anim", Object.fromEntries(Object.entries(cat.anim_texto).filter(([k2]) => k2 !== "escribir")), st.anim) +
            range("s-inicio", "Aparece en", 0, Math.max(0.5, T - 0.3), 0.1, st.inicio, " s") + range("s-fin", "Se va en", 0.3, T, 0.1, st.fin, " s");
        }
        case "ritmo":
          return `<p class="rx-hint">Ajusta la duración de cada clip para que los cortes caigan en los golpes de la música elegida${p.opciones.music === "none" ? " (primero elegí una música)" : ""}.</p>
            <div class="rx-grid4"><button type="button" class="rx-btn" data-a="ritmo" data-v="1">Cada golpe</button><button type="button" class="rx-btn" data-a="ritmo" data-v="2">Cada 2</button>
            <button type="button" class="rx-btn" data-a="ritmo" data-v="4">Cada 4 (un compás)</button><button type="button" class="rx-btn" data-a="ritmo" data-v="8">Cada 8</button></div>
            <label class="rx-sw"><input type="checkbox" class="rx-keep-tr"><span>Mantener las transiciones (si no, cortes secos)</span></label>`;
        case "titulo":
          return `<label class="rx-l">Título <small>*entre asteriscos* va en naranja</small><input type="text" data-k="title" value="${esc(o.title)}" placeholder="Así vivimos el *Event Hub*"></label>
            <label class="rx-l">Subtítulo<input type="text" data-k="subtitle" value="${esc(o.subtitle)}" placeholder="Asunción · Octubre 2026"></label>
            <p class="rx-hint">Aparece los primeros 3,5 segundos. En la próxima entrega se suman textos libres en cualquier momento del reel.</p>`;
        case "marca":
          return `<label class="rx-sw"><input type="checkbox" data-k="watermark" ${o.watermark ? "checked" : ""}><span>Logo chico arriba durante el reel</span></label>
            <label class="rx-sw"><input type="checkbox" data-k="outro" ${o.outro !== false ? "checked" : ""}><span>Cierre con el logo (3 s)</span></label>
            <select data-k="logo" class="rx-sel"><option value="auto">Logo automático (según el fondo)</option>
            ${(opts.logos || []).map(n => `<option value="${esc(n)}" ${o.logo === n ? "selected" : ""}>${esc(n.replace(/\.(png|webp)$/i, ""))}</option>`).join("")}</select>`;
      }
      return "";
    }

    function bindPanel(k, c) {
      const o = p.opciones;
      // deslizadores: en vivo al mover, al historial al soltar
      body.querySelectorAll("input[type=range][data-k]").forEach(r => {
        r.oninput = () => {
          const v = parseFloat(r.value), key = r.dataset.k;
          r.closest(".rx-r").querySelector("output").textContent = fmt(v) + r.dataset.suf;
          if (/^[ts]-/.test(key)) {
            const it = key[0] === "t" ? p.textos[selT] : p.stickers[selS], f = key.slice(2);
            it[f] = v;
            if (f === "inicio" && it.fin < v + 0.3) it.fin = v + 0.3;
            if (f === "fin" && it.inicio > v - 0.3) it.inicio = Math.max(0, v - 0.3);
            overlay(); lanes();
            if (f === "inicio" && video.duration) { video.pause(); video.currentTime = Math.min(video.duration - 0.05, v + 0.3); }
            return;
          }
          if (k === "transicion") p.clips[trans][key] = v;
          else if (["music_volume", "music_start", "music_fade_out", "voz_volume"].includes(key)) o[key] = v;
          else if (key === "dur") { c.start = 0; c.end = v; c.source_duration = v; }
          else if (key === "start") { c.start = Math.min(v, c.end - MIN * c.speed); seek(c.start); }
          else if (key === "end") { c.end = Math.max(v, c.start + MIN * c.speed); seek(c.end - 0.05); }
          else if (key === "split") { /* solo elige el punto */ }
          else c[key] = v;
          if (k === "ajustes") body.querySelector(".rx-look img").style.filter = cssLook(c);
          $(".rx-total").textContent = tc(total(p));
        };
        r.onchange = () => { if (r.dataset.k !== "split") commit(); if (["start", "end"].includes(r.dataset.k)) openTool(k); };
      });
      body.querySelectorAll("button[data-k]").forEach(b => b.onclick = () => {
        const key = b.dataset.k, v = b.dataset.v;
        if (/^[ts]-/.test(key)) { (key[0] === "t" ? p.textos[selT] : p.stickers[selS])[key.slice(2)] = v; commit(); return openTool(k); }
        if (k === "transicion") p.clips[trans].transition = v;
        else if (key === "formato") o.formato = v;
        else if (key === "filtro-global") { p.clips.forEach(x => { x.filtro = v; }); toast("Filtro aplicado a todos los clips."); }
        else if (key === "speed") c.speed = parseFloat(v);
        else c[key] = v;
        commit(); openTool(k);
      });
      body.querySelectorAll("input[type=checkbox][data-k]").forEach(x => x.onchange = () => {
        const key = x.dataset.k;
        if (key === "sound") { c.mute = !x.checked; if (x.checked && !c.volume) c.volume = 1; }
        else o[key] = x.checked;
        commit();
      });
      body.querySelectorAll("input[type=text][data-k]").forEach(x => { x.oninput = () => { o[x.dataset.k] = x.value; }; x.onchange = commit; });
      body.querySelectorAll("select[data-k]").forEach(x => x.onchange = () => { o[x.dataset.k] = x.value; commit(); openTool(k); });
      const pick = body.querySelector("[data-k=fondo-pick]");
      if (pick) { pick.oninput = () => { c.fondo = pick.value; }; pick.onchange = () => { commit(); openTool(k); }; }
      body.querySelectorAll("[data-a]").forEach(b => {
        if (b.tagName === "INPUT") b.onchange = () => panelAction(b.dataset.a, c, b);
        else b.onclick = () => panelAction(b.dataset.a, c, b);
      });
      // texto elegido
      if (k === "texto-ed") {
        const t = p.textos[selT];
        const ta = body.querySelector("[data-tk=texto]");
        ta.oninput = () => { t.texto = ta.value; overlay(); lanes(); };
        ta.onchange = commit;
        body.querySelectorAll("[data-tpos]").forEach(b => b.onclick = () => { t.y = +b.dataset.tpos; t.x = 0.5; commit(); });
        body.querySelectorAll("[data-tcol]").forEach(b => b.onclick = () => { t.color = b.dataset.tcol; commit(); openTool(k); });
        body.querySelectorAll("[data-tbox]").forEach(b => b.onclick = () => { t.caja = b.dataset.tbox; commit(); openTool(k); });
        body.querySelectorAll("[data-tchk]").forEach(x => x.onchange = () => { t[x.dataset.tchk] = x.checked; commit(); });
      }
      if (k === "sticker-ed") {
        const st = p.stickers[selS];
        body.querySelectorAll("[data-scol]").forEach(b => b.onclick = () => { st.color = b.dataset.scol; commit(); openTool(k); });
        const lg = body.querySelector("[data-sk=logo]");
        if (lg) lg.onchange = () => { st.logo = lg.value; commit(); };
      }
      // video del tramo (recortar / dividir / congelar)
      const sv = body.querySelector(".rx-scrub video");
      if (sv) {
        const pos = body.querySelector(".rx-pos");
        if (pos) {
          const at = body.querySelector(".rx-at");
          const show = () => { if (sv.readyState) sv.currentTime = +pos.value; at.textContent = `${fmt(+pos.value - c.start)} s desde el inicio del clip`; };
          sv.onloadedmetadata = show;
          pos.oninput = show; show();
        } else {
          sv.onloadedmetadata = () => { sv.currentTime = c.start; sv.play().catch(() => {}); };
          sv.ontimeupdate = () => { if (sv.currentTime >= c.end || sv.currentTime < c.start - 0.3) sv.currentTime = c.start; };
          sv.onclick = () => sv.paused ? sv.play() : sv.pause();
        }
      }
    }
    function seek(t) { const sv = body.querySelector(".rx-scrub video"); if (sv && sv.readyState) { sv.pause(); sv.currentTime = t; } }

    async function panelAction(a, c, el) {
      const o = p.opciones;
      if (a === "split") {
        if (c.kind === "foto") {
          const t = +body.querySelector("[data-k=split]").value;
          if (t < 0.3 || c.end - t < 0.3) return toast("Cada parte tiene que durar al menos 0,3 s.");
          const b = { ...clone(c), id: uid(), start: 0, end: +(c.end - t).toFixed(2), source_duration: +(c.end - t).toFixed(2) };
          c.end = t; c.source_duration = t; c.transition = "none";
          p.clips.splice(sel + 1, 0, b);
        } else {
          const t = +body.querySelector(".rx-pos").value;
          if (t - c.start < MIN * c.speed || c.end - t < MIN * c.speed) return toast("Cada parte tiene que durar al menos 0,3 s.");
          const b = { ...clone(c), id: uid(), start: t };
          c.end = t; c.transition = "none";
          p.clips.splice(sel + 1, 0, b);
        }
        toast("Dividido en dos: ahora cada parte se edita por separado.");
        commit(); return openTool("dividir");
      }
      if (a === "freeze") {
        const t = +body.querySelector(".rx-pos").value;
        el.disabled = true; el.textContent = "Sacando el cuadro…";
        try {
          const r = await fetch("/api/reel/cuadro", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lote, src: c.src, t }) });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error);
          // el clip se parte en ese cuadro y la imagen congelada queda en el medio
          const frozen = { ...j.clip, transition: "none" };
          if (t - c.start >= MIN * c.speed && c.end - t >= MIN * c.speed) {
            const after = { ...clone(c), id: uid(), start: t };
            const tr = c.transition, ts = c.transition_seconds;
            c.end = t; c.transition = "none";
            after.transition = tr; after.transition_seconds = ts;
            p.clips.splice(sel + 1, 0, frozen, after);
          } else p.clips.splice(sel + 1, 0, frozen);
          sel++; toast("Imagen congelada de 2 s agregada."); commit(); openTool("duracion");
        } catch (err) { toast("No se pudo congelar: " + err.message); el.disabled = false; el.textContent = "Congelar este cuadro (2 s)"; }
        return;
      }
      if (a === "add-text") return addText(el.dataset.v);
      if (a === "pick-text") return selectLayer("t", +el.dataset.v);
      if (a === "add-sticker") return addSticker(el.dataset.v);
      if (a === "ritmo") return alRitmo(+el.dataset.v, body.querySelector(".rx-keep-tr").checked);
      switch (a) {
        case "centrar": c.zoom = 1; c.pan_x = 0; c.pan_y = 0; break;
        case "filtro-todos": p.clips.forEach(x => { x.filtro = c.filtro; }); toast("Filtro aplicado a todos los clips."); break;
        case "reset-ajustes": Object.assign(c, { brillo: 0, contraste: 0, saturacion: 0, temperatura: 0, vineta: 0 }); break;
        case "rot-l": c.rotate = ((c.rotate || 0) + 270) % 360; break;
        case "rot-r": c.rotate = ((c.rotate || 0) + 90) % 360; break;
        case "flip-h": c.flip_h = !c.flip_h; break;
        case "flip-v": c.flip_v = !c.flip_v; break;
        case "izq": if (sel > 0) { [p.clips[sel - 1], p.clips[sel]] = [p.clips[sel], p.clips[sel - 1]]; sel--; } break;
        case "der": if (sel < p.clips.length - 1) { [p.clips[sel + 1], p.clips[sel]] = [p.clips[sel], p.clips[sel + 1]]; sel++; } break;
        case "trans-todas": { const t = p.clips[trans]; p.clips.slice(0, -1).forEach(x => { x.transition = t.transition; x.transition_seconds = t.transition_seconds; }); toast("Transición aplicada a todos los cortes."); break; }
        case "otra-cancion": o.music_seed = Math.floor(Math.random() * 1e6) + 1; toast("Melodía nueva: se escucha en la vista previa."); break;
        case "quitar-voz": o.voz = ""; p.voz_url = null; break;
        case "grabar": return grabar(el);
        case "voz-archivo": return subirVoz(el.files[0]);
      }
      commit(); openTool(tool);
    }

    // --- voz en off: grabar con el micrófono del celular ---------------------------
    let rec = null;
    async function grabar(btn) {
      if (rec) { rec.stop(); return; }
      if (!navigator.mediaDevices || !window.MediaRecorder) return toast("Este navegador no permite grabar. Subí un audio.");
      let stream;
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (_) { return toast("Sin permiso para el micrófono. Activalo en los ajustes del celular."); }
      const type = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find(t => MediaRecorder.isTypeSupported(t)) || "";
      const chunks = [];
      rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      const t0 = Date.now();
      const tick = setInterval(() => {
        const s = (Date.now() - t0) / 1000, el = body.querySelector(".rx-rect");
        if (el) el.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
      }, 250);
      rec.onstop = async () => {
        clearInterval(tick); stream.getTracks().forEach(t => t.stop()); rec = null;
        btn.classList.remove("on"); btn.querySelector("span").textContent = "Grabar";
        const ext = type.includes("mp4") ? "m4a" : "webm";
        await subirVoz(new File(chunks, `voz-${Date.now()}.${ext}`, { type: type || "audio/webm" }));
      };
      rec.start(); btn.classList.add("on"); btn.querySelector("span").textContent = "Parar";
    }
    async function subirVoz(file) {
      if (!file) return;
      toast("Subiendo la voz…");
      try {
        const [ref] = await window.subirArchivos([file], () => {});
        const r = await fetch("/api/reel/voz", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lote, ref }) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error);
        p.opciones.voz = j.voz; p.voz_url = j.url;
        toast(`Voz agregada (${fmt(j.segundos)} s).`); commit(); openTool("voz");
      } catch (err) { toast("No se pudo agregar la voz: " + err.message); }
    }

    // --- guardar este reel como plantilla propia ---------------------------------------
    async function guardarPlantilla() {
      const nombre = prompt("Nombre de la plantilla (cada clip queda como un espacio con su estilo, textos y stickers incluidos):",
        p.plantilla ? p.plantilla + " (mía)" : "Mi plantilla");
      if (!nombre) return;
      try {
        const r = await fetch("/api/reel/guardar-plantilla", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lote, nombre, proyecto: p }) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error);
        toast(`Guardada. La encontrás en Reels → Con plantilla.`);
      } catch (err) { toast("No se pudo guardar: " + err.message); }
    }

    // --- agregar clips ----------------------------------------------------------------
    function addClips() {
      const inp = document.createElement("input");
      inp.type = "file"; inp.accept = "video/*,image/*"; inp.multiple = true;
      inp.onchange = async () => {
        const fl = [...inp.files];
        if (!fl.length) return;
        busyOn("Subiendo…");
        try {
          const refs = await window.subirArchivos(fl, t => busyText(t));
          busyText("Preparando los clips nuevos…");
          const r = await fetch("/api/reel/agregar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lote, refs }) });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error);
          const at = sel >= 0 ? sel + 1 : p.clips.length;
          p.clips.splice(at, 0, ...j.clips);
          sel = at; commit(); toast(`${j.clips.length} clip${j.clips.length > 1 ? "s" : ""} agregado${j.clips.length > 1 ? "s" : ""}.`);
        } catch (err) { toast("No se pudieron agregar: " + err.message); }
        finally { busyOff(); }
      };
      inp.click();
    }

    // --- vista previa y exportar ----------------------------------------------------------
    const busyOn = t => { busy = true; $(".rx-busy").hidden = false; busyText(t); root.querySelectorAll(".rx-top button").forEach(b => { b.disabled = b.dataset.x !== "cerrar"; }); };
    const busyText = t => { $(".rx-busy p").textContent = t; };
    const busyOff = () => { busy = false; $(".rx-busy").hidden = true; root.querySelectorAll(".rx-top button").forEach(b => { b.disabled = false; }); paint(); };

    async function render(preview) {
      if (busy) return;
      clearTimeout(autoT);
      if (autoBusy) { toast(preview ? "Ya se está actualizando la vista previa." : "Esperá unos segundos: termina la vista previa y exporta."); if (!preview) setTimeout(() => render(false), 2500); return; }
      const want = snap();
      busyOn(preview ? "Armando la vista previa…" : "Exportando en alta calidad… podés salir de la app: te aviso al terminar.");
      try {
        const r = await fetch("/api/reel/editar", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lote, proyecto: p, vista_previa: preview }) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "No se pudo.");
        if (!preview && window.seguirTrabajo) window.seguirTrabajo(j.job, "reel", false);  // sigue en segundo plano
        const t0 = Date.now();
        let s;
        do {
          await new Promise(ok => setTimeout(ok, 1500));
          try { s = await (await fetch("/api/trabajo/" + j.job)).json(); } catch (_) { s = { estado: "procesando" }; }
          if (s.estado === "procesando") busyText(`${s.progreso || (preview ? "Armando la vista previa" : "Exportando")}… ${Math.round((Date.now() - t0) / 1000)} s`);
        } while (s.estado === "procesando");
        if (s.estado === "error") throw new Error(s.error);
        archivo = s.archivo; video.src = archivo; video.load(); video.play().catch(() => {});
        rendered = want;
        if (preview) {
          estadoCambios();
        } else {
          saved = clone(s.proyecto); p = clone(s.proyecto); p.textos = p.textos || []; p.stickers = p.stickers || [];
          last = snap(); hist.length = 0; fut.length = 0;
          localStorage.removeItem(KEY);
          rendered = exported = snap();
          estadoCambios();
          $(".rx-badge").textContent = `Versión ${saved.version} · lista para descargar`;
          toast("Listo. Ya podés descargarla desde la pantalla anterior (✕).");
          if (cardBox) open(cardBox, { ...s, ...cat }, opts);
        }
      } catch (err) { toast(String(err.message || err)); }
      finally { busyOff(); }
    }

    // --- acciones de arriba ---------------------------------------------------------------
    root.querySelectorAll("[data-z]").forEach(b => b.onclick = () => { PPS = Math.max(16, Math.min(140, PPS * (b.dataset.z === "1" ? 1.35 : 1 / 1.35))); paint(); });
    $("[data-x=undo]").onclick = undo;
    $("[data-x=redo]").onclick = redo;
    $("[data-x=previa]").onclick = () => render(true);
    $("[data-x=exportar]").onclick = () => render(false);
    $("[data-x=cerrar]").onclick = () => {
      if (rec) rec.stop();
      root.remove(); document.body.classList.remove("rx-abierto");
    };

    let toastT = null;
    function toast(t) {
      let el = root.querySelector(".rx-toast");
      if (!el) { el = document.createElement("div"); el.className = "rx-toast"; el.setAttribute("role", "status"); root.appendChild(el); }
      el.textContent = t; el.classList.add("on");
      clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove("on"), 3200);
    }

    paint();
    if (recuperado) { exported = ""; programarPrevia(); }
    if (recuperado) toast("Recuperé los cambios que no habías exportado.");
    else if (info.borrador) toast("Seguís desde tu última vista previa.");
  }

  return { open, editor };
})();
