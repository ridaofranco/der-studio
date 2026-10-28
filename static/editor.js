/* DER Studio — composición y edición de piezas (Fabric.js 5).
 *
 * Un diseño = { name, W, H, base (url del JPG de fondo), layers: [...] }
 * Una vez editado se guarda además `fabric` (JSON de Fabric) para reabrirlo tal cual.
 */
(function () {
  const BRAND = { naranja: "#ff5c00", oscuro: "#333333", claro: "#f0f0f0", blanco: "#ffffff" };
  const FAMILIES = { title: "DER Titulo", subtitle: "DER Sub", body: "DER Cuerpo" };
  const EXTRA = ["name", "logo", "role"];
  const FS_MULT = 1.13; // fabric.Text._fontSizeMult

  async function loadFonts() {
    await Promise.all(Object.values(FAMILIES).map(f => document.fonts.load(`40px "${f}"`)));
  }

  const loadImage = (url, opts = {}) =>
    new Promise((ok, fail) => fabric.Image.fromURL(url, img => img ? ok(img) : fail(url), opts));

  async function layerToObject(l) {
    if (l.type === "text") {
      return new fabric.Textbox(l.text, {
        left: l.x, top: l.y, width: l.w + Math.ceil(l.size * 0.15), fontFamily: l.family,
        fontSize: l.size, fill: l.color, lineHeight: l.lineGap / FS_MULT, styles: toStyles(l.styles),
        textAlign: l.align || "left", name: l.name, role: l.font,
      });
    }
    if (l.type === "rect") {
      return new fabric.Rect({ left: l.x, top: l.y, width: l.w, height: l.h, fill: l.color, name: l.name });
    }
    const img = await loadImage(l.src);
    img.set({ left: l.x, top: l.y, scaleX: l.w / img.width, scaleY: l.h / img.height, name: l.name, logo: l.logo || null });
    return img;
  }

  function toStyles(s) {
    const out = {};
    for (const li in s || {}) { out[+li] = {}; for (const ci in s[li]) out[+li][+ci] = s[li][ci]; }
    return out;
  }

  /** Arma el diseño completo en un canvas de Fabric (estático o editable). */
  async function build(canvas, design) {
    await loadFonts();
    canvas.clear();
    const bg = await loadImage(design.base);
    bg.set({ scaleX: design.W / bg.width, scaleY: design.H / bg.height });
    canvas.setBackgroundImage(bg, () => {});
    if (design.fabric) {
      await new Promise(ok => canvas.loadFromJSON({ ...design.fabric, backgroundImage: undefined }, ok));
      canvas.setBackgroundImage(bg, () => {});
    } else {
      for (const l of design.layers) canvas.add(await layerToObject(l));
    }
    // color de fondo: se ve donde la base es transparente (todo menos las fotos)
    canvas.backgroundColor = (design.fabric && design.fabric.background) || design.bg || BRAND.claro;
    canvas.renderAll();
  }

  /** Compone el diseño a resolución completa y devuelve un Blob JPG. */
  async function render(design) {
    const el = document.createElement("canvas");
    const c = new fabric.StaticCanvas(el, { width: design.W, height: design.H, enableRetinaScaling: false });
    await build(c, design);
    const url = c.toDataURL({ format: "jpeg", quality: 0.93 });
    c.dispose();
    return (await fetch(url)).blob();
  }

  // ---------------------------------------------------------------------------
  // Editor
  // ---------------------------------------------------------------------------
  let ed = null; // estado del editor abierto

  function ui() {
    const wrap = document.createElement("div");
    wrap.className = "ed";
    wrap.innerHTML = `
      <div class="ed-stage"><canvas></canvas></div>
      <aside class="ed-side">
        <div class="ed-top">
          <button data-a="undo" title="Deshacer (Ctrl+Z)">↶</button>
          <button data-a="redo" title="Rehacer (Ctrl+Y)">↷</button>
          <span class="ed-name"></span>
        </div>
        <h3>Agregar</h3>
        <div class="ed-btns">
          <button data-add="texto">Texto</button>
          <button data-add="barra">Barra</button>
          <button data-add="esquinero">Esquinero</button>
          <button data-add="puntos">Puntos</button>
        </div>
        <select class="ed-addlogo"><option value="">+ Agregar logo…</option></select>
        <h3>Fondo</h3>
        <div class="ed-sw ed-bg">
          ${Object.entries(BRAND).map(([k, v]) => `<button data-bg="${v}" title="Fondo ${k}" style="background:${v}"></button>`).join("")}
          <label class="ed-otro" title="Otro color"><input type="color" data-bgpick><span>Otro</span></label>
        </div>

        <div class="ed-sel" hidden>
          <h3>Seleccionado: <span class="ed-selname"></span></h3>
          <div class="ed-text">
            <label>Texto</label>
            <textarea data-p="text" rows="3"></textarea>
            <label>Tipografía</label>
            <select data-p="role"><option value="title">Títulos (Netron)</option><option value="subtitle">Subtítulos (Articulat)</option><option value="body">Texto (Jost)</option></select>
            <label>Tamaño <output></output></label>
            <input type="range" data-p="fontSize" min="12" max="320">
            <div class="ed-btns ed-align">
              <button data-align="left">Izq.</button><button data-align="center">Centro</button><button data-align="right">Der.</button>
              <button data-a="upper" title="Pasar a mayúsculas">AA</button>
            </div>
          </div>
          <div class="ed-logo">
            <label>Cambiar logo</label>
            <select data-p="logo"></select>
          </div>
          <div class="ed-color">
            <label>Color <small class="ed-colorhint"></small></label>
            <div class="ed-sw">
              ${Object.entries(BRAND).map(([k, v]) => `<button data-color="${v}" title="${k}" style="background:${v}"></button>`).join("")}
            </div>
          </div>
          <label>Opacidad</label>
          <input type="range" data-p="opacity" min="0.1" max="1" step="0.05">
          <div class="ed-btns">
            <button data-a="dup">Duplicar</button>
            <button data-a="front">Al frente</button>
            <button data-a="back">Atrás</button>
            <button data-a="del" class="ed-danger">Eliminar</button>
          </div>
        </div>
        <p class="ed-tip">Arrastrá para mover · esquinas para agrandar · <b>doble clic (o el campo "Texto") para escribir</b>.
          Para resaltar palabras: seleccionalas mientras escribís y tocá un color.</p>
        <div class="ed-foot">
          <button data-a="cancel" class="ed-sec">Cancelar</button>
          <button data-a="save" class="ed-prim">Guardar</button>
        </div>
      </aside>`;
    document.body.appendChild(wrap);
    return wrap;
  }

  async function open(design, { logos = [], onSave } = {}) {
    await loadFonts();
    const root = ui();
    const $ = s => root.querySelector(s);
    const stage = $(".ed-stage");
    const canvas = new fabric.Canvas(root.querySelector("canvas"), {
      preserveObjectStacking: true, selectionColor: "rgba(255,92,0,.08)", selectionBorderColor: BRAND.naranja,
    });
    const touch = matchMedia("(pointer: coarse)").matches;
    fabric.Object.prototype.set({ borderColor: BRAND.naranja, cornerColor: BRAND.naranja, cornerStyle: "circle", transparentCorners: false,
      cornerSize: touch ? 22 : 12, touchCornerSize: 44, padding: touch ? 6 : 0 });
    ed = { canvas, design, root, history: [], future: [], restoring: false };
    $(".ed-name").textContent = design.name;

    // Lista de logos (para agregar o reemplazar)
    const logoOpts = [["auto:on_dark", "Automático · fondo oscuro"], ["auto:on_light", "Automático · fondo claro"], ["auto:on_orange", "Automático · fondo naranja"],
      ...logos.map(n => ["file:" + n, n.replace(/\.(png|webp)$/i, "")])];
    const optsHtml = logoOpts.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
    $(".ed-addlogo").insertAdjacentHTML("beforeend", optsHtml);
    $("[data-p=logo]").innerHTML = optsHtml;

    const fit = () => {
      const r = stage.getBoundingClientRect();
      const z = Math.min((r.width - 24) / design.W, (r.height - 24) / design.H);
      canvas.setDimensions({ width: design.W * z, height: design.H * z });
      canvas.setZoom(z);
      ed.zoom = z;
    };
    fit();
    window.addEventListener("resize", fit);
    await build(canvas, design);
    snapshot();

    // Guías de centrado
    const guides = { v: false, h: false };
    canvas.on("object:moving", e => {
      const o = e.target, tol = 10 / ed.zoom, c = o.getCenterPoint();
      guides.v = Math.abs(c.x - design.W / 2) < tol;
      guides.h = Math.abs(c.y - design.H / 2) < tol;
      if (guides.v) o.setPositionByOrigin(new fabric.Point(design.W / 2, c.y), "center", "center");
      if (guides.h) o.setPositionByOrigin(new fabric.Point(o.getCenterPoint().x, design.H / 2), "center", "center");
    });
    canvas.on("after:render", () => {
      if (!guides.v && !guides.h) return;
      const ctx = canvas.getContext(), z = ed.zoom;
      ctx.save(); ctx.strokeStyle = "#ff00aa"; ctx.lineWidth = 1; ctx.setLineDash([6, 4]);
      if (guides.v) { ctx.beginPath(); ctx.moveTo(design.W / 2 * z, 0); ctx.lineTo(design.W / 2 * z, design.H * z); ctx.stroke(); }
      if (guides.h) { ctx.beginPath(); ctx.moveTo(0, design.H / 2 * z); ctx.lineTo(design.W * z, design.H / 2 * z); ctx.stroke(); }
      ctx.restore();
    });
    canvas.on("mouse:up", () => { guides.v = guides.h = false; canvas.requestRenderAll(); });

    // Textos: al escalar, cambiar el tamaño de letra en vez de estirar
    canvas.on("object:modified", e => {
      const o = e.target;
      if (o && o.type === "textbox" && (o.scaleX !== 1 || o.scaleY !== 1)) {
        o.set({ fontSize: Math.round(o.fontSize * o.scaleY), width: o.width * o.scaleX, scaleX: 1, scaleY: 1 });
        o.initDimensions();
      }
      snapshot(); syncPanel();
    });
    ["object:added", "object:removed"].forEach(ev => canvas.on(ev, () => snapshot()));
    canvas.on("text:editing:exited", () => snapshot());
    ["selection:created", "selection:updated", "selection:cleared"].forEach(ev => canvas.on(ev, syncPanel));
    canvas.on("text:selection:changed", syncPanel);

    // --- Panel ---
    function syncPanel() {
      const o = canvas.getActiveObject();
      $(".ed-sel").hidden = !o;
      if (!o) return;
      const isText = o.type === "textbox";
      const isLogo = !!o.logo;
      $(".ed-selname").textContent = o.name || (isText ? "Texto" : "Elemento");
      $(".ed-text").hidden = !isText;
      $(".ed-logo").hidden = !isLogo;
      $(".ed-color").hidden = isLogo;
      if (isText) {
        if (document.activeElement !== $("[data-p=text]")) $("[data-p=text]").value = o.text;
        $("[data-p=role]").value = o.role || "body";
        $("[data-p=fontSize]").value = o.fontSize;
        $(".ed-text output").textContent = Math.round(o.fontSize) + " px";
        const sel = o.isEditing && o.selectionStart !== o.selectionEnd;
        $(".ed-colorhint").textContent = sel ? "(solo lo seleccionado)" : "";
      } else $(".ed-colorhint").textContent = "";
      if (isLogo) $("[data-p=logo]").value = o.logo;
      $("[data-p=opacity]").value = o.opacity ?? 1;
    }

    const active = () => canvas.getActiveObject();
    $("[data-p=text]").oninput = e => { const o = active(); if (!o || o.type !== "textbox") return; o.set("text", e.target.value); o.initDimensions(); canvas.requestRenderAll(); };
    $("[data-p=text]").onchange = () => snapshot();
    $("[data-p=role]").onchange = e => { const o = active(); o.set({ role: e.target.value, fontFamily: FAMILIES[e.target.value] }); o.initDimensions(); canvas.requestRenderAll(); snapshot(); };
    $("[data-p=fontSize]").oninput = e => { const o = active(); o.set("fontSize", +e.target.value); o.initDimensions(); $(".ed-text output").textContent = e.target.value + " px"; canvas.requestRenderAll(); };
    $("[data-p=fontSize]").onchange = () => snapshot();
    $("[data-p=opacity]").oninput = e => { active().set("opacity", +e.target.value); canvas.requestRenderAll(); };
    $("[data-p=opacity]").onchange = () => snapshot();
    $("[data-p=logo]").onchange = async e => {
      const o = active(), w = o.getScaledWidth();
      await new Promise(ok => o.setSrc(logoUrl(e.target.value), ok));
      const s = w / o.width; o.set({ scaleX: s, scaleY: s, logo: e.target.value });
      canvas.requestRenderAll(); snapshot();
    };
    root.querySelectorAll("[data-align]").forEach(b => b.onclick = () => { active().set("textAlign", b.dataset.align); canvas.requestRenderAll(); snapshot(); });
    root.querySelectorAll("[data-color]").forEach(b => b.onclick = async () => {
      const o = active(), color = b.dataset.color;
      if (!o) return;
      if (o.type === "textbox") {
        if (o.isEditing && o.selectionStart !== o.selectionEnd) o.setSelectionStyles({ fill: color });
        else { o.set("fill", color); o.styles = {}; }
      } else if (o.type === "rect") o.set("fill", color);
      else if (o.type === "image") {
        const src = o.getSrc();
        if (src.includes("/elemento/")) {
          const u = new URL(src, location.href); u.searchParams.set("color", color.slice(1));
          const w = o.getScaledWidth(), h = o.getScaledHeight();
          await new Promise(ok => o.setSrc(u.pathname + u.search, ok));
          o.set({ scaleX: w / o.width, scaleY: h / o.height });
        }
      }
      canvas.requestRenderAll(); snapshot();
    });

    const center = obj => { obj.set({ left: design.W / 2 - obj.getScaledWidth() / 2, top: design.H / 2 - obj.getScaledHeight() / 2 }); return obj; };
    const s = design.W / 1080;
    root.querySelectorAll("[data-add]").forEach(b => b.onclick = async () => {
      let o;
      const k = b.dataset.add;
      if (k === "texto") o = new fabric.Textbox("Texto nuevo", { width: 600 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 56 * s, fill: BRAND.blanco, name: "Texto" });
      if (k === "barra") o = new fabric.Rect({ width: 90 * s, height: 10 * s, fill: BRAND.naranja, name: "Barra" });
      if (k === "esquinero") { o = await loadImage(`/elemento/esquinero.png?c=tl&l=${Math.round(110 * s)}&g=${Math.round(10 * s)}&color=ff5c00`); o.set({ name: "Esquinero" }); }
      if (k === "puntos") { o = await loadImage(`/elemento/puntos.png?cols=6&rows=4&gap=${Math.round(28 * s)}&r=${Math.round(4 * s)}&color=ff5c00`); o.set({ name: "Puntos" }); }
      canvas.add(center(o)); canvas.setActiveObject(o); canvas.requestRenderAll();
    });
    $(".ed-addlogo").onchange = async e => {
      if (!e.target.value) return;
      const o = await loadImage(logoUrl(e.target.value));
      const sc = 260 * s / o.width;
      o.set({ scaleX: sc, scaleY: sc, name: "Logo", logo: e.target.value });
      canvas.add(center(o)); canvas.setActiveObject(o); e.target.value = "";
    };

    const actions = {
      undo() { if (ed.history.length > 1) { ed.future.push(ed.history.pop()); restore(ed.history.at(-1)); } },
      redo() { if (ed.future.length) { const st = ed.future.pop(); ed.history.push(st); restore(st); } },
      upper() { const o = active(); o.set("text", o.text.toUpperCase()); canvas.requestRenderAll(); snapshot(); },
      dup() { active().clone(c => { c.set({ left: c.left + 30, top: c.top + 30 }); canvas.add(c); canvas.setActiveObject(c); }, EXTRA); },
      front() { active().bringToFront(); snapshot(); },
      back() { active().sendToBack(); snapshot(); },
      del() { canvas.getActiveObjects().forEach(o => canvas.remove(o)); canvas.discardActiveObject(); canvas.requestRenderAll(); },
      cancel() { close(); },
      async save() {
        canvas.discardActiveObject(); canvas.renderAll();
        const z = ed.zoom;
        const url = canvas.toDataURL({ format: "jpeg", quality: 0.93, multiplier: 1 / z });
        design.fabric = canvas.toJSON(EXTRA);
        delete design.fabric.backgroundImage;
        const blob = await (await fetch(url)).blob();
        close();
        onSave && onSave(design, blob);
      },
    };
    root.querySelectorAll("[data-a]").forEach(b => b.onclick = () => actions[b.dataset.a]());

    // Fondo: cambia el color liso de la pieza (las fotos no se tocan)
    // Si un elemento queda del mismo color que el fondo nuevo, pasa al color de marca que contrasta
    const contrast = bg => {
      const c = bg.toLowerCase();
      if (c === BRAND.naranja) return BRAND.oscuro;
      return luminance(c) < 0.45 ? BRAND.claro : BRAND.oscuro;
    };
    function luminance(hex) {
      const m = /^#?([0-9a-f]{6})$/i.exec(hex); if (!m) return 1;
      const n = parseInt(m[1], 16);
      return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    }
    const same = (a, b) => typeof a === "string" && a.toLowerCase() === b.toLowerCase();
    async function fixClashes(bg) {
      const alt = contrast(bg);
      for (const o of canvas.getObjects()) {
        if (same(o.fill, bg)) o.set("fill", alt);
        if (o.styles) for (const li in o.styles) for (const ci in o.styles[li]) {
          // las palabras resaltadas tienen que seguir distinguiéndose del resto del texto
          if (same(o.styles[li][ci].fill, bg)) o.styles[li][ci].fill = same(bg, BRAND.naranja) ? BRAND.blanco : alt;
        }
        const src = o.getSrc && o.getSrc();
        if (src && src.includes("/elemento/") && src.includes("color=" + bg.slice(1).toLowerCase())) {
          await new Promise(ok => o.setSrc(src.replace("color=" + bg.slice(1).toLowerCase(), "color=" + alt.slice(1)), ok));
        }
        o.dirty = true;
      }
    }
    const setBg = async (color, fix = true) => {
      canvas.backgroundColor = color;
      if (fix) await fixClashes(color);
      canvas.requestRenderAll(); snapshot();
      root.querySelectorAll("[data-bg]").forEach(b => b.classList.toggle("on", b.dataset.bg.toLowerCase() === color.toLowerCase()));
      $("[data-bgpick]").value = /^#[0-9a-f]{6}$/i.test(color) ? color : "#333333";
    };
    root.querySelectorAll("[data-bg]").forEach(b => b.onclick = () => setBg(b.dataset.bg));
    $("[data-bgpick]").oninput = e => setBg(e.target.value);
    setBg(canvas.backgroundColor || BRAND.claro, false);

    function onKey(e) {
      const o = active();
      const typing = (o && o.isEditing) || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); actions.undo(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y" && !typing) { e.preventDefault(); actions.redo(); return; }
      if (e.key === "Escape" && !typing) { close(); return; }
      if (!o || typing) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); actions.del(); }
      const step = e.shiftKey ? 10 : 1;
      const mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (mv) { e.preventDefault(); o.set({ left: o.left + mv[0], top: o.top + mv[1] }); o.setCoords(); canvas.requestRenderAll(); snapshot(); }
    }
    document.addEventListener("keydown", onKey);

    function snapshot() {
      if (ed.restoring) return;
      const st = JSON.stringify(canvas.toJSON(EXTRA));
      if (ed.history.at(-1) === st) return;
      ed.history.push(st); if (ed.history.length > 60) ed.history.shift();
      ed.future = [];
    }
    function restore(st) {
      ed.restoring = true;
      const bg = canvas.backgroundImage;
      canvas.loadFromJSON(st, () => { canvas.setBackgroundImage(bg, () => {}); canvas.renderAll(); ed.restoring = false; syncPanel(); });
    }
    function close() {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", fit);
      canvas.dispose(); root.remove(); ed = null;
    }
  }

  const logoUrl = key => "/logos/ver/" + encodeURIComponent(key).replace("%3A", ":");

  window.DEREditor = { render, open, loadFonts };
})();
