/* DER Studio — composición y edición de piezas (Fabric.js 5), al estilo Canva.
 *
 * Un diseño = { name, W, H, base (url de la imagen de fondo), bg (color), layers: [...] }
 * Una vez editado se guarda además `fabric` (JSON de Fabric) para reabrirlo tal cual.
 *
 * Panel lateral con pestañas:
 *   sin selección → Agregar · Capas · Fondo
 *   con selección → Editar · Posición · Capas
 * Posición: alinear a la página (o entre elementos si hay varios), distribuir, orden, girar,
 * espejar, X/Y/ancho/alto exactos, bloquear, agrupar. Guías inteligentes contra los bordes y
 * centros de los demás elementos y contra los márgenes seguros. Copiar y pegar entre piezas,
 * copiar estilo (como la brocha de Canva).
 */
(function () {
  const BRAND = { naranja: "#ff5c00", oscuro: "#333333", claro: "#f0f0f0", blanco: "#ffffff" };
  const FAMILIES = { title: "DER Titulo", subtitle: "DER Sub", body: "DER Cuerpo" };
  const EXTRA = ["name", "logo", "role", "bloqueado"];
  const FS_MULT = 1.13; // fabric.Text._fontSizeMult
  const CLIP_KEY = "derPortapapeles";

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

  /** Bloquear o desbloquear un elemento (se puede elegir igual, para desbloquearlo). */
  function applyLock(o, on) {
    o.set({ bloqueado: !!on, lockMovementX: !!on, lockMovementY: !!on, lockScalingX: !!on, lockScalingY: !!on,
      lockRotation: !!on, hasControls: !on, editable: o.type === "textbox" ? !on : o.editable });
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
    canvas.getObjects().forEach(o => { if (o.bloqueado) applyLock(o, true); });
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

  const IC = { // íconos 24×24 (trazo)
    undo: "M9 14 4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3", redo: "m15 14 5-5-5-5M20 9H9a5 5 0 0 0 0 10h3",
    copy: "M8 8h12v12H8zM4 16V4h12", paste: "M9 4h6v3H9zM7 6H5v15h14V6h-2", brush: "M14 4l6 6-8 8H6v-6zM4 20h4",
    lock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3", unlock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 7.5-2",
    eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    eyeoff: "M3 3l18 18M10.6 6.1A10 10 0 0 1 12 6c6 0 10 6 10 6a17 17 0 0 1-3 3.6M6.3 6.3C3.7 8 2 12 2 12s4 6 10 6a9 9 0 0 0 4-.9",
    al: "M4 4v16M8 7h12v4H8zM8 13h7v4H8z", ac: "M12 3v18M6 7h12v4H6zM8 13h8v4H8z", ar: "M20 4v16M4 7h12v4H4zM9 13h7v4H9z",
    at: "M4 4h16M7 8h4v12H7zM13 8h4v7h-4z", am: "M3 12h18M7 6h4v12H7zM13 8h4v8h-4z", ab: "M4 20h16M7 4h4v12H7zM13 9h4v7h-4z",
    dh: "M4 4v16M20 4v16M9 8h6v8H9z", dv: "M4 4h16M4 20h16M8 9h8v6H8z",
    up: "M12 19V5M6 11l6-6 6 6", down: "M12 5v14M6 13l6 6 6-6", top: "M5 4h14M12 20V8M6 14l6-6 6 6", bottom: "M5 20h14M12 4v12M6 10l6 6 6-6",
    fliph: "M12 3v18M4 7l5 5-5 5zM20 7l-5 5 5 5z", flipv: "M3 12h18M7 4l5 5 5-5zM7 20l5-5 5 5z",
    group: "M4 4h7v7H4zM13 13h7v7h-7zM14 6h4v4M6 14v4h4", ungroup: "M4 4h7v7H4zM13 13h7v7h-7z",
    dup: "M8 8h12v12H8zM4 16V4h12", del: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  };
  const ico = n => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${IC[n]}"/></svg>`;

  function ui() {
    const wrap = document.createElement("div");
    wrap.className = "ed";
    wrap.innerHTML = `
      <div class="ed-stage"><canvas></canvas><div class="ed-zoomlbl"></div></div>
      <aside class="ed-side">
        <div class="ed-top">
          <button data-a="undo" title="Deshacer (Ctrl+Z)" aria-label="Deshacer">${ico("undo")}</button>
          <button data-a="redo" title="Rehacer (Ctrl+Y)" aria-label="Rehacer">${ico("redo")}</button>
          <button data-a="copy" title="Copiar (Ctrl+C)" aria-label="Copiar">${ico("copy")}</button>
          <button data-a="paste" title="Pegar (Ctrl+V), también en otra pieza" aria-label="Pegar">${ico("paste")}</button>
          <span class="ed-name"></span>
        </div>
        <div class="ed-tabs" role="tablist"></div>
        <div class="ed-panel"></div>
        <div class="ed-foot">
          <button data-a="cancel" class="ed-sec">Cancelar</button>
          <button data-a="save" class="ed-prim">Guardar</button>
        </div>
      </aside>`;
    document.body.appendChild(wrap);
    return wrap;
  }

  async function open(design, { logos = [], onSave, siblings = [], onSaveOther } = {}) {
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
    let tab = "agregar", multi = false, styleClip = null;

    const logoOpts = [["auto:on_dark", "Automático · fondo oscuro"], ["auto:on_light", "Automático · fondo claro"], ["auto:on_orange", "Automático · fondo naranja"],
      ...logos.map(n => ["file:" + n, n.replace(/\.(png|webp)$/i, "")])];
    const logoOptsHtml = sel => logoOpts.map(([v, t]) => `<option value="${v}" ${v === sel ? "selected" : ""}>${t}</option>`).join("");

    const fit = () => {
      const r = stage.getBoundingClientRect();
      const z = Math.min((r.width - 24) / design.W, (r.height - 24) / design.H);
      canvas.setDimensions({ width: design.W * z, height: design.H * z });
      canvas.setZoom(z);
      ed.zoom = z;
      $(".ed-zoomlbl").textContent = Math.round(z * 100) + "%";
    };
    fit();
    window.addEventListener("resize", fit);
    await build(canvas, design);
    snapshot();

    // --- Guías inteligentes: bordes y centros de la página, de los márgenes y de los demás elementos ---
    const isStory = design.H / design.W > 1.6;
    const margin = { x: design.W * 0.074, top: isStory ? 230 * design.W / 1080 : design.H * 0.06, bottom: isStory ? 330 * design.W / 1080 : design.H * 0.06 };
    let guideLines = [];
    canvas.on("object:moving", e => {
      const o = e.target, tol = 8 / ed.zoom;
      const r = o.getBoundingRect(true, true);
      const xs = [0, design.W / 2, design.W, margin.x, design.W - margin.x];
      const ys = [0, design.H / 2, design.H, margin.top, design.H - margin.bottom];
      const moving = new Set(o.type === "activeSelection" ? o.getObjects() : [o]);
      canvas.getObjects().forEach(x => {
        if (moving.has(x) || !x.visible) return;
        const b = x.getBoundingRect(true, true);
        xs.push(b.left, b.left + b.width / 2, b.left + b.width);
        ys.push(b.top, b.top + b.height / 2, b.top + b.height);
      });
      guideLines = [];
      const cand = (pos, lines) => { // [delta, línea] más cercano para los 3 puntos del elemento
        let best = null;
        for (const [p, off] of pos) for (const L of lines) {
          const d = L - p;
          if (Math.abs(d) < tol && (!best || Math.abs(d) < Math.abs(best[0]))) best = [d, L];
        }
        return best;
      };
      const bx = cand([[r.left, 0], [r.left + r.width / 2, 0], [r.left + r.width, 0]], xs);
      const by = cand([[r.top, 0], [r.top + r.height / 2, 0], [r.top + r.height, 0]], ys);
      if (bx) { o.left += bx[0]; guideLines.push(["v", bx[1]]); }
      if (by) { o.top += by[0]; guideLines.push(["h", by[1]]); }
      o.setCoords();
    });
    canvas.on("after:render", () => {
      if (!guideLines.length) return;
      const ctx = canvas.getContext(), z = ed.zoom;
      ctx.save(); ctx.strokeStyle = "#ff2bd6"; ctx.lineWidth = 1; ctx.setLineDash([5, 4]);
      for (const [t, v] of guideLines) {
        ctx.beginPath();
        if (t === "v") { ctx.moveTo(v * z, 0); ctx.lineTo(v * z, design.H * z); } else { ctx.moveTo(0, v * z); ctx.lineTo(design.W * z, v * z); }
        ctx.stroke();
      }
      ctx.restore();
    });
    canvas.on("mouse:up", () => { if (guideLines.length) { guideLines = []; canvas.requestRenderAll(); } });

    // Textos: al escalar, cambiar el tamaño de letra en vez de estirar
    canvas.on("object:modified", e => {
      const o = e.target;
      if (o && o.type === "textbox" && (o.scaleX !== 1 || o.scaleY !== 1)) {
        o.set({ fontSize: Math.round(o.fontSize * o.scaleY), width: o.width * o.scaleX, scaleX: 1, scaleY: 1 });
        o.initDimensions();
      }
      snapshot(); panel();
    });
    ["object:added", "object:removed"].forEach(ev => canvas.on(ev, () => { snapshot(); if (tab === "capas") panel(); }));
    canvas.on("text:editing:exited", () => snapshot());
    canvas.on("selection:created", () => { if (["agregar", "fondo"].includes(tab)) tab = "editar"; panel(); });
    canvas.on("selection:updated", () => panel());
    // al alinear o distribuir la selección se rearma: esperar un instante antes de cambiar de pestaña
    canvas.on("selection:cleared", () => setTimeout(() => {
      if (active()) return;
      if (["editar", "posicion"].includes(tab)) tab = "agregar";
      panel();
    }, 0));
    canvas.on("text:selection:changed", () => { if (tab === "editar") syncText(); });

    // Seleccionar varios en el celular: con el modo activo, cada toque suma a la selección
    canvas.on("mouse:down", e => {
      if (!multi || !e.target) return;
      const cur = canvas.getActiveObjects().filter(x => x !== e.target);
      const set = canvas.getActiveObjects().includes(e.target) && cur.length ? cur : [...new Set([...cur, e.target])];
      setTimeout(() => {
        canvas.discardActiveObject();
        canvas.setActiveObject(set.length > 1 ? new fabric.ActiveSelection(set, { canvas }) : set[0]);
        canvas.requestRenderAll();
      }, 0);
    });

    const active = () => canvas.getActiveObject();

    // --- Panel con pestañas ---------------------------------------------------------
    function panel() {
      const o = active();
      const tabs = o ? [["editar", "Editar"], ["posicion", "Posición"], ["capas", "Capas"]] : [["agregar", "Agregar"], ["capas", "Capas"], ["fondo", "Fondo"]];
      if (!tabs.some(([k]) => k === tab)) tab = tabs[0][0];
      $(".ed-tabs").innerHTML = tabs.map(([k, n]) => `<button data-tab="${k}" role="tab" class="${k === tab ? "on" : ""}">${n}</button>`).join("");
      $(".ed-tabs").querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { tab = b.dataset.tab; panel(); });
      const html = { agregar: agregarHTML, capas: capasHTML, fondo: fondoHTML, editar: editarHTML, posicion: posicionHTML }[tab]();
      $(".ed-panel").innerHTML = html;
      bind();
      $("[data-a=paste]").disabled = !localStorage.getItem(CLIP_KEY);
      $("[data-a=copy]").disabled = !o;
    }

    function agregarHTML() {
      return `<div class="ed-grid2">
          <button data-add="texto" class="ed-card"><b class="ed-ct">Aa</b><span>Texto</span></button>
          <button data-add="titulo" class="ed-card"><b class="ed-ct t">TÍTULO</b><span>Título</span></button>
          <button data-add="barra" class="ed-card"><i class="ed-cbar"></i><span>Barra</span></button>
          <button data-add="esquinero" class="ed-card"><i class="ed-ccor"></i><span>Esquinero</span></button>
          <button data-add="puntos" class="ed-card"><i class="ed-cdots"></i><span>Puntos</span></button>
        </div>
        <label>Logo</label><select class="ed-addlogo"><option value="">+ Agregar logo…</option>${logoOptsHtml("")}</select>
        <p class="ed-tip">Tocá un elemento para editarlo. Para elegir varios: arrastrá un recuadro, Shift + clic, o el botón <b>Elegir varios</b>.</p>
        <button class="ed-wide ${multi ? "on" : ""}" data-a="multi">${multi ? "✓ Elegir varios activado" : "Elegir varios"}</button>`;
    }

    function fondoHTML() {
      const bg = (canvas.backgroundColor || "").toLowerCase();
      return `<label>Color de fondo</label><div class="ed-sw ed-bg">
          ${Object.entries(BRAND).map(([k, v]) => `<button data-bg="${v}" title="Fondo ${k}" class="${bg === v ? "on" : ""}" style="background:${v}"></button>`).join("")}
          <label class="ed-otro" title="Otro color"><input type="color" data-bgpick value="${/^#[0-9a-f]{6}$/i.test(bg) ? bg : "#333333"}"><span>Otro</span></label>
        </div><p class="ed-tip">Cambia el fondo liso de la pieza (las fotos no se tocan). Lo que queda del mismo color que el fondo pasa solo a un color que contraste.</p>`;
    }

    const kindName = o => o.type === "activeSelection" ? `${o.getObjects().length} elementos` : o.type === "group" ? "Grupo" :
      o.name || (o.type === "textbox" ? "Texto" : o.logo ? "Logo" : "Elemento");

    function capasHTML() {
      const objs = canvas.getObjects().slice().reverse(), sel = new Set(canvas.getActiveObjects());
      if (!objs.length) return `<p class="ed-tip">La pieza no tiene elementos.</p>`;
      return `<p class="ed-tip" style="margin-top:0">Arriba = adelante. Arrastrá para cambiar el orden.</p><ul class="ed-layers">${objs.map(o => {
        const i = canvas.getObjects().indexOf(o);
        const label = o.type === "textbox" ? (o.text || "").replace(/\s+/g, " ").slice(0, 34) : kindName(o);
        const kind = o.type === "textbox" ? "T" : o.logo ? "L" : o.type === "group" ? "G" : "■";
        return `<li draggable="true" data-i="${i}" class="${sel.has(o) ? "on" : ""}${o.visible === false ? " off" : ""}">
          <span class="ed-lk">${kind}</span><span class="ed-ln">${esc(label || kindName(o))}</span>
          <button data-vis="${i}" title="${o.visible === false ? "Mostrar" : "Ocultar"}" aria-label="Mostrar u ocultar">${ico(o.visible === false ? "eyeoff" : "eye")}</button>
          <button data-lock="${i}" title="${o.bloqueado ? "Desbloquear" : "Bloquear"}" aria-label="Bloquear" class="${o.bloqueado ? "on" : ""}">${ico(o.bloqueado ? "lock" : "unlock")}</button></li>`;
      }).join("")}</ul>`;
    }

    function editarHTML() {
      const o = active();
      const isText = o.type === "textbox", isLogo = !!o.logo, isSel = o.type === "activeSelection";
      let h = `<h3>${esc(kindName(o))}${o.bloqueado ? " · bloqueado" : ""}</h3>`;
      if (isText) {
        h += `<label>Texto</label><textarea data-p="text" rows="3">${esc(o.text)}</textarea>
          <label>Tipografía</label><select data-p="role">
            <option value="title" ${o.role === "title" ? "selected" : ""}>Títulos (Netron)</option>
            <option value="subtitle" ${o.role === "subtitle" ? "selected" : ""}>Subtítulos (Articulat)</option>
            <option value="body" ${o.role === "body" || !o.role ? "selected" : ""}>Texto (Jost)</option></select>
          <label>Tamaño <output>${Math.round(o.fontSize)} px</output></label><input type="range" data-p="fontSize" min="12" max="320" value="${o.fontSize}">
          <div class="ed-btns ed-align">
            <button data-align="left" class="${o.textAlign === "left" ? "on" : ""}">Izq.</button><button data-align="center" class="${o.textAlign === "center" ? "on" : ""}">Centro</button>
            <button data-align="right" class="${o.textAlign === "right" ? "on" : ""}">Der.</button><button data-a="upper" title="Pasar a mayúsculas">AA</button>
          </div>`;
      }
      if (isLogo) {
        h += `<label>Cambiar logo</label><select data-p="logo">${logoOptsHtml(o.logo)}</select>
          <button data-a="replicar" class="ed-wide ed-replicar">Replicar en todas las piezas</button>
          <p class="ed-rep-hint">Mismo logo, mismo tamaño y mismo lugar en el resto de las piezas de este lote.</p>`;
      }
      if (!isLogo) {
        h += `<label>Color <small class="ed-colorhint"></small></label><div class="ed-sw">
          ${Object.entries(BRAND).map(([k, v]) => `<button data-color="${v}" title="${k}" style="background:${v}"></button>`).join("")}
          <label class="ed-otro" title="Otro color"><input type="color" data-colorpick value="${typeof o.fill === "string" && /^#[0-9a-f]{6}$/i.test(o.fill) ? o.fill : "#ff5c00"}"></label></div>`;
      }
      h += `<label>Transparencia <output>${Math.round((o.opacity ?? 1) * 100)}%</output></label><input type="range" data-p="opacity" min="0.05" max="1" step="0.05" value="${o.opacity ?? 1}">
        <div class="ed-tools">
          <button data-a="dup">${ico("dup")}<span>Duplicar</span></button>
          <button data-a="copystyle" class="${styleClip ? "on" : ""}">${ico("brush")}<span>${styleClip ? "Pegar estilo" : "Copiar estilo"}</span></button>
          ${isSel ? `<button data-a="group">${ico("group")}<span>Agrupar</span></button>` : ""}
          ${o.type === "group" ? `<button data-a="ungroup">${ico("ungroup")}<span>Desagrupar</span></button>` : ""}
          <button data-a="lock" class="${o.bloqueado ? "on" : ""}">${ico(o.bloqueado ? "lock" : "unlock")}<span>${o.bloqueado ? "Desbloquear" : "Bloquear"}</span></button>
          <button data-a="del" class="ed-danger">${ico("del")}<span>Eliminar</span></button>
        </div>`;
      if (styleClip) h += `<p class="ed-tip">Estilo copiado: tocá otro elemento y después <b>Pegar estilo</b>. (Tocá dos veces para soltarlo.)</p>`;
      if (isText) h += `<p class="ed-tip">Doble toque sobre el texto para escribir. Para resaltar palabras: seleccionalas mientras escribís y tocá un color.</p>`;
      return h;
    }

    function posicionHTML() {
      const o = active(), many = o.type === "activeSelection";
      const r = o.getBoundingRect(true, true);
      const btn = (a, ic, t) => `<button data-al="${a}" title="${t}" aria-label="${t}">${ico(ic)}</button>`;
      return `<h3>${many ? "Alinear entre sí" : "Alinear a la página"}</h3>
        <div class="ed-alg">${btn("left", "al", "Izquierda")}${btn("hcenter", "ac", "Centro")}${btn("right", "ar", "Derecha")}
          ${btn("top", "at", "Arriba")}${btn("vcenter", "am", "Medio")}${btn("bottom", "ab", "Abajo")}</div>
        ${many ? `<h3>Distribuir</h3><div class="ed-alg two">${btn("dh", "dh", "Espaciado horizontal parejo")}${btn("dv", "dv", "Espaciado vertical parejo")}</div>
          <button class="ed-wide sec" data-a="page-center">Centrar el grupo en la página</button>` : ""}
        <h3>Orden</h3>
        <div class="ed-tools four">
          <button data-ord="front">${ico("top")}<span>Al frente</span></button><button data-ord="up">${ico("up")}<span>Adelante</span></button>
          <button data-ord="down">${ico("down")}<span>Atrás</span></button><button data-ord="back">${ico("bottom")}<span>Al fondo</span></button>
        </div>
        <h3>Girar y espejar</h3>
        <div class="ed-row3"><label class="ed-num">Giro<input type="number" data-n="angle" value="${Math.round(o.angle || 0)}" step="1"><i>°</i></label>
          <button data-a="fliph" class="ed-ib" title="Espejar horizontal">${ico("fliph")}</button><button data-a="flipv" class="ed-ib" title="Espejar vertical">${ico("flipv")}</button></div>
        <h3>Posición y tamaño <small>(px de la pieza)</small></h3>
        <div class="ed-nums">
          <label class="ed-num">X<input type="number" data-n="x" value="${Math.round(r.left)}"></label>
          <label class="ed-num">Y<input type="number" data-n="y" value="${Math.round(r.top)}"></label>
          <label class="ed-num">Ancho<input type="number" data-n="w" value="${Math.round(r.width)}" min="1"></label>
          <label class="ed-num">Alto<input type="number" data-n="h" value="${Math.round(r.height)}" min="1"></label>
        </div>
        <label class="ed-chk"><input type="checkbox" data-n="ratio" checked> Mantener proporción</label>
        <p class="ed-tip">Al arrastrar, los elementos se pegan a los bordes, al centro, a los márgenes seguros y a los demás elementos (línea rosa).</p>`;
    }

    const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

    function syncText() {
      const o = active();
      if (!o || o.type !== "textbox") return;
      const sel = o.isEditing && o.selectionStart !== o.selectionEnd;
      const hint = $(".ed-colorhint");
      if (hint) hint.textContent = sel ? "(solo lo seleccionado)" : "";
      const ta = $("[data-p=text]");
      if (ta && document.activeElement !== ta) ta.value = o.text;
    }

    // --- acciones del panel ---------------------------------------------------------
    function bind() {
      const P = $(".ed-panel");
      P.querySelectorAll("[data-a]").forEach(b => b.onclick = () => actions[b.dataset.a]());
      P.querySelectorAll("[data-add]").forEach(b => b.onclick = () => addElement(b.dataset.add));
      const al = P.querySelector(".ed-addlogo");
      if (al) al.onchange = async e => {
        if (!e.target.value) return;
        const o = await loadImage(logoUrl(e.target.value));
        const sc = 260 * s / o.width;
        o.set({ scaleX: sc, scaleY: sc, name: "Logo", logo: e.target.value });
        canvas.add(center(o)); canvas.setActiveObject(o); canvas.requestRenderAll();
      };
      // fondo
      P.querySelectorAll("[data-bg]").forEach(b => b.onclick = () => setBg(b.dataset.bg));
      const bp = P.querySelector("[data-bgpick]");
      if (bp) bp.oninput = e => setBg(e.target.value);
      // capas
      P.querySelectorAll(".ed-layers li").forEach(li => {
        const i = +li.dataset.i, o = canvas.getObjects()[i];
        li.onclick = e => { if (e.target.closest("button")) return; canvas.setActiveObject(o); canvas.requestRenderAll(); tab = "capas"; panel(); };
        li.ondragstart = e => { e.dataTransfer.setData("text/plain", i); li.classList.add("drag"); };
        li.ondragend = () => li.classList.remove("drag");
        li.ondragover = e => e.preventDefault();
        li.ondrop = e => {
          e.preventDefault();
          const from = +e.dataTransfer.getData("text/plain"), obj = canvas.getObjects()[from];
          if (obj) { canvas.moveTo(obj, i); canvas.requestRenderAll(); snapshot(); panel(); }
        };
        // en el celular no hay arrastrar nativo: mantener apretado y deslizar
        touchReorder(li, i);
      });
      P.querySelectorAll("[data-vis]").forEach(b => b.onclick = () => {
        const o = canvas.getObjects()[+b.dataset.vis];
        o.visible = o.visible === false; if (!o.visible) canvas.discardActiveObject();
        canvas.requestRenderAll(); snapshot(); panel();
      });
      P.querySelectorAll("[data-lock]").forEach(b => b.onclick = () => {
        const o = canvas.getObjects()[+b.dataset.lock];
        applyLock(o, !o.bloqueado); canvas.requestRenderAll(); snapshot(); panel();
      });
      // editar
      const o = active();
      const ta = P.querySelector("[data-p=text]");
      if (ta) { ta.oninput = () => { o.set("text", ta.value); o.initDimensions(); canvas.requestRenderAll(); }; ta.onchange = () => snapshot(); }
      const role = P.querySelector("[data-p=role]");
      if (role) role.onchange = () => { o.set({ role: role.value, fontFamily: FAMILIES[role.value] }); o.initDimensions(); canvas.requestRenderAll(); snapshot(); };
      const fs = P.querySelector("[data-p=fontSize]");
      if (fs) { fs.oninput = () => { o.set("fontSize", +fs.value); o.initDimensions(); fs.previousElementSibling.querySelector("output").textContent = fs.value + " px"; canvas.requestRenderAll(); }; fs.onchange = () => snapshot(); }
      const op = P.querySelector("[data-p=opacity]");
      if (op) { op.oninput = () => { o.set("opacity", +op.value); op.previousElementSibling.querySelector("output").textContent = Math.round(op.value * 100) + "%"; canvas.requestRenderAll(); }; op.onchange = () => snapshot(); }
      const lg = P.querySelector("[data-p=logo]");
      if (lg) lg.onchange = async () => {
        const w = o.getScaledWidth();
        await new Promise(ok => o.setSrc(logoUrl(lg.value), ok));
        const sc = w / o.width; o.set({ scaleX: sc, scaleY: sc, logo: lg.value });
        canvas.requestRenderAll(); snapshot();
      };
      P.querySelectorAll("[data-align]").forEach(b => b.onclick = () => { o.set("textAlign", b.dataset.align); canvas.requestRenderAll(); snapshot(); panel(); });
      P.querySelectorAll("[data-color]").forEach(b => b.onclick = () => paint(b.dataset.color));
      const cp = P.querySelector("[data-colorpick]");
      if (cp) cp.onchange = () => paint(cp.value);
      // posición
      P.querySelectorAll("[data-al]").forEach(b => b.onclick = () => align(b.dataset.al));
      P.querySelectorAll("[data-ord]").forEach(b => b.onclick = () => order(b.dataset.ord));
      P.querySelectorAll("[data-n]").forEach(inp => { if (inp.type === "number") inp.onchange = () => numeric(inp.dataset.n, +inp.value); });
    }

    function touchReorder(li, i) {
      let timer = null, startY = 0, moving = false;
      li.addEventListener("touchstart", e => {
        if (e.target.closest("button")) return;
        startY = e.touches[0].clientY;
        timer = setTimeout(() => { moving = true; li.classList.add("drag"); }, 350);
      }, { passive: true });
      li.addEventListener("touchmove", e => {
        if (!moving) { if (Math.abs(e.touches[0].clientY - startY) > 6) clearTimeout(timer); return; }
        e.preventDefault();
        li.style.transform = `translateY(${e.touches[0].clientY - startY}px)`;
      }, { passive: false });
      li.addEventListener("touchend", e => {
        clearTimeout(timer);
        if (!moving) return;
        moving = false; li.classList.remove("drag"); li.style.transform = "";
        const y = e.changedTouches[0].clientY;
        const items = [...li.parentElement.children];
        const target = items.find(x => { const r = x.getBoundingClientRect(); return y >= r.top && y <= r.bottom; });
        if (target && target !== li) {
          const obj = canvas.getObjects()[i];
          canvas.moveTo(obj, +target.dataset.i); canvas.requestRenderAll(); snapshot(); panel();
        }
      });
    }

    async function paint(color) {
      const o = active();
      if (!o) return;
      const targets = o.type === "activeSelection" || o.type === "group" ? o.getObjects() : [o];
      for (const t of targets) {
        if (t.type === "textbox") {
          if (t.isEditing && t.selectionStart !== t.selectionEnd) t.setSelectionStyles({ fill: color });
          else { t.set("fill", color); t.styles = {}; }
        } else if (t.type === "rect" || t.type === "circle" || t.type === "path" || t.type === "polygon") t.set("fill", color);
        else if (t.type === "image") {
          const src = t.getSrc();
          if (src.includes("/elemento/")) {
            const u = new URL(src, location.href); u.searchParams.set("color", color.slice(1));
            const w = t.getScaledWidth(), h = t.getScaledHeight();
            await new Promise(ok => t.setSrc(u.pathname + u.search, ok));
            t.set({ scaleX: w / t.width, scaleY: h / t.height });
          }
        }
        t.dirty = true;
      }
      canvas.requestRenderAll(); snapshot();
    }

    // alinear: un elemento → a la página; varios → entre ellos (dentro del recuadro de la selección)
    function align(how) {
      const o = active();
      if (!o) return;
      if (how === "dh" || how === "dv") return distribute(how);
      if (o.type === "activeSelection") {
        const sb = o.getBoundingRect(true, true), objs = o.getObjects();
        canvas.discardActiveObject();
        objs.forEach(x => moveRect(x, how, sb));
        canvas.setActiveObject(new fabric.ActiveSelection(objs, { canvas }));
      } else moveRect(o, how, { left: 0, top: 0, width: design.W, height: design.H });
      canvas.requestRenderAll(); snapshot(); panel();
    }
    function moveRect(x, how, box) {
      const r = x.getBoundingRect(true, true);
      let dx = 0, dy = 0;
      if (how === "left") dx = box.left - r.left;
      if (how === "hcenter") dx = box.left + box.width / 2 - (r.left + r.width / 2);
      if (how === "right") dx = box.left + box.width - (r.left + r.width);
      if (how === "top") dy = box.top - r.top;
      if (how === "vcenter") dy = box.top + box.height / 2 - (r.top + r.height / 2);
      if (how === "bottom") dy = box.top + box.height - (r.top + r.height);
      x.set({ left: x.left + dx, top: x.top + dy }); x.setCoords();
    }
    function distribute(how) {
      const o = active();
      if (o.type !== "activeSelection") return;
      const objs = o.getObjects().slice();
      if (objs.length < 3) return toast("Para distribuir elegí 3 elementos o más.");
      canvas.discardActiveObject();
      const key = how === "dh" ? ["left", "width"] : ["top", "height"];
      const rects = objs.map(x => [x, x.getBoundingRect(true, true)]).sort((a, b) => a[1][key[0]] - b[1][key[0]]);
      const first = rects[0][1], last = rects[rects.length - 1][1];
      const span = last[key[0]] + last[key[1]] - first[key[0]];
      const used = rects.reduce((a, [, r]) => a + r[key[1]], 0);
      const gap = (span - used) / (rects.length - 1);
      let pos = first[key[0]];
      rects.forEach(([x, r]) => { const d = pos - r[key[0]]; x.set(key[0], x[key[0]] + d); x.setCoords(); pos += r[key[1]] + gap; });
      canvas.setActiveObject(new fabric.ActiveSelection(objs, { canvas }));
      canvas.requestRenderAll(); snapshot(); panel();
    }
    function order(how) {
      const o = active();
      if (!o) return;
      const list = o.type === "activeSelection" ? o.getObjects() : [o];
      if (how === "front") list.forEach(x => x.bringToFront());
      if (how === "back") list.slice().reverse().forEach(x => x.sendToBack());
      if (how === "up") list.slice().reverse().forEach(x => x.bringForward());
      if (how === "down") list.forEach(x => x.sendBackwards());
      canvas.requestRenderAll(); snapshot();
    }
    function numeric(k, v) {
      const o = active();
      if (!o || Number.isNaN(v)) return;
      const r = o.getBoundingRect(true, true);
      const ratio = $(".ed-panel [data-n=ratio]")?.checked;
      if (k === "x") o.set("left", o.left + (v - r.left));
      if (k === "y") o.set("top", o.top + (v - r.top));
      if (k === "angle") { o.rotate(v); }
      if ((k === "w" || k === "h") && v > 0) {
        if (o.type === "textbox" && k === "w") { o.set("width", o.width * v / r.width); o.initDimensions(); }
        else {
          const fx = k === "w" ? v / r.width : (ratio ? v / r.height : 1);
          const fy = k === "h" ? v / r.height : (ratio ? v / r.width : 1);
          o.set({ scaleX: o.scaleX * fx, scaleY: o.scaleY * fy });
        }
      }
      o.setCoords(); canvas.requestRenderAll(); snapshot(); panel();
    }

    const center = obj => { obj.set({ left: design.W / 2 - obj.getScaledWidth() / 2, top: design.H / 2 - obj.getScaledHeight() / 2 }); return obj; };
    const s = design.W / 1080;
    async function addElement(k) {
      let o;
      if (k === "texto") o = new fabric.Textbox("Texto nuevo", { width: 600 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 56 * s, fill: BRAND.blanco, name: "Texto" });
      if (k === "titulo") o = new fabric.Textbox("TÍTULO", { width: 800 * s, fontFamily: FAMILIES.title, role: "title", fontSize: 110 * s, fill: BRAND.blanco, name: "Título", textAlign: "center" });
      if (k === "barra") o = new fabric.Rect({ width: 90 * s, height: 10 * s, fill: BRAND.naranja, name: "Barra" });
      if (k === "esquinero") { o = await loadImage(`/elemento/esquinero.png?c=tl&l=${Math.round(110 * s)}&g=${Math.round(10 * s)}&color=ff5c00`); o.set({ name: "Esquinero" }); }
      if (k === "puntos") { o = await loadImage(`/elemento/puntos.png?cols=6&rows=4&gap=${Math.round(28 * s)}&r=${Math.round(4 * s)}&color=ff5c00`); o.set({ name: "Puntos" }); }
      if (!o) return;
      canvas.add(center(o)); canvas.setActiveObject(o); canvas.requestRenderAll();
    }

    // --- copiar estilo (brocha) ---------------------------------------------------------
    const STYLE_KEYS = ["fill", "fontFamily", "role", "fontSize", "fontWeight", "fontStyle", "underline", "textAlign", "lineHeight",
      "charSpacing", "stroke", "strokeWidth", "shadow", "opacity", "rx", "ry", "textBackgroundColor"];
    function copyStyle() {
      const o = active();
      if (!o) return;
      if (styleClip) { // pegar
        const targets = o.type === "activeSelection" ? o.getObjects() : [o];
        targets.forEach(t => {
          Object.entries(styleClip).forEach(([k, v]) => {
            if (v === undefined) return;
            if (k === "fontSize" && t.type !== "textbox") return;
            if (["fontFamily", "role", "textAlign", "lineHeight", "charSpacing", "fontWeight", "fontStyle", "underline", "textBackgroundColor"].includes(k) && t.type !== "textbox") return;
            if (k === "fill" && t.type === "image") return;
            t.set(k, k === "shadow" && v ? new fabric.Shadow(v) : v);
          });
          if (t.type === "textbox") { t.styles = {}; t.initDimensions(); }
        });
        styleClip = null; canvas.requestRenderAll(); snapshot(); toast("Estilo pegado."); return panel();
      }
      styleClip = {};
      STYLE_KEYS.forEach(k => { if (o[k] !== undefined) styleClip[k] = k === "shadow" && o.shadow ? o.shadow.toObject() : o[k]; });
      toast("Estilo copiado. Elegí otro elemento y tocá Pegar estilo.");
      panel();
    }

    // --- copiar y pegar (sirve entre piezas: se guarda en el navegador) -------------------
    function copy() {
      const o = active();
      if (!o) return;
      o.clone(c => {
        const data = c.type === "activeSelection" ? { multi: true, objects: c.getObjects().map(x => x.toObject(EXTRA)), left: c.left, top: c.top, W: design.W }
          : { multi: false, objects: [c.toObject(EXTRA)], W: design.W };
        if (c.type === "activeSelection") {
          // pasar a coordenadas absolutas
          const m = c.calcTransformMatrix();
          data.objects = c.getObjects().map(x => {
            const p = fabric.util.transformPoint({ x: x.left, y: x.top }, m);
            return { ...x.toObject(EXTRA), left: p.x, top: p.y };
          });
        }
        localStorage.setItem(CLIP_KEY, JSON.stringify(data));
        $("[data-a=paste]").disabled = false;
        toast(`Copiado${data.objects.length > 1 ? ` (${data.objects.length} elementos)` : ""}. Podés pegarlo acá o en otra pieza.`);
      }, EXTRA);
    }
    function paste() {
      const raw = localStorage.getItem(CLIP_KEY);
      if (!raw) return;
      const data = JSON.parse(raw), k = design.W / (data.W || design.W);
      fabric.util.enlivenObjects(data.objects, objs => {
        const sameSpot = data.W === design.W && !canvas.getObjects().some(x => objs.some(n => Math.abs(x.left - n.left) < 1 && Math.abs(x.top - n.top) < 1));
        batch(() => objs.forEach(n => {
          n.set({ left: n.left * k + (sameSpot ? 0 : 24), top: n.top * k + (sameSpot ? 0 : 24), scaleX: n.scaleX * k, scaleY: n.scaleY * k });
          if (n.bloqueado) applyLock(n, true);
          canvas.add(n);
        }));
        canvas.discardActiveObject();
        canvas.setActiveObject(objs.length > 1 ? new fabric.ActiveSelection(objs, { canvas }) : objs[0]);
        canvas.requestRenderAll(); snapshot(); panel();
      });
    }

    const actions = {
      undo() { if (ed.history.length > 1) { ed.future.push(ed.history.pop()); restore(ed.history.at(-1)); } },
      redo() { if (ed.future.length) { const st = ed.future.pop(); ed.history.push(st); restore(st); } },
      upper() { const o = active(); o.set("text", o.text.toUpperCase()); canvas.requestRenderAll(); snapshot(); panel(); },
      dup() {
        active().clone(c => {
          canvas.discardActiveObject();
          if (c.type === "activeSelection") {
            c.canvas = canvas;
            batch(() => c.forEachObject(x => canvas.add(x)));
            c.set({ left: c.left + 30, top: c.top + 30 }); c.setCoords();
          } else { c.set({ left: c.left + 30, top: c.top + 30 }); canvas.add(c); }
          canvas.setActiveObject(c); canvas.requestRenderAll(); snapshot();
        }, EXTRA);
      },
      del() { const list = canvas.getActiveObjects(); canvas.discardActiveObject(); batch(() => list.forEach(o => canvas.remove(o))); canvas.requestRenderAll(); },
      lock() { const o = active(); const on = !o.bloqueado; (o.type === "activeSelection" ? o.getObjects() : [o]).forEach(x => applyLock(x, on)); if (o.type === "activeSelection") applyLock(o, on); canvas.requestRenderAll(); snapshot(); panel(); },
      group() { const o = active(); if (o.type !== "activeSelection") return; const g = o.toGroup(); g.set({ name: "Grupo" }); canvas.requestRenderAll(); snapshot(); panel(); },
      ungroup() { const o = active(); if (o.type !== "group") return; o.toActiveSelection(); canvas.requestRenderAll(); snapshot(); panel(); },
      fliph() { const o = active(); o.set("flipX", !o.flipX); canvas.requestRenderAll(); snapshot(); },
      flipv() { const o = active(); o.set("flipY", !o.flipY); canvas.requestRenderAll(); snapshot(); },
      "page-center"() { const o = active(); moveRect(o, "hcenter", { left: 0, top: 0, width: design.W, height: design.H }); moveRect(o, "vcenter", { left: 0, top: 0, width: design.W, height: design.H }); canvas.requestRenderAll(); snapshot(); },
      multi() { multi = !multi; toast(multi ? "Tocá los elementos que querés juntar." : "Elegir varios: desactivado."); panel(); },
      copystyle: copyStyle, copy, paste,
      cancel() { close(); },

      // Replicar el logo elegido en las demás piezas del lote: mismo archivo, tamaño, posición y opacidad.
      // Si la otra pieza ya tiene ese logo (o su logo principal), se reemplaza; no queda duplicado.
      async replicar() {
        const o = active();
        if (!o || !o.logo) return;
        const others = siblings.filter(d => d !== design);
        const btn = $(".ed-replicar"), hint = $(".ed-rep-hint");
        if (!others.length || !onSaveOther) { hint.textContent = "No hay otras piezas en este lote."; return; }
        const principal = canvas.getObjects().find(x => x.logo) === o;
        const spec = { key: o.logo, src: o.getSrc(), left: o.left, top: o.top, scaleX: o.scaleX, scaleY: o.scaleY,
          angle: o.angle || 0, opacity: o.opacity ?? 1, name: o.name || "Logo", W: design.W, H: design.H, cy: o.getCenterPoint().y };
        btn.disabled = true;
        let ok = 0;
        try {
          for (const [k, d] of others.entries()) {
            hint.textContent = `Aplicando en ${k + 1} de ${others.length}…`;
            const el = document.createElement("canvas");
            const c = new fabric.StaticCanvas(el, { width: d.W, height: d.H, enableRetinaScaling: false });
            await build(c, d);
            const logosT = c.getObjects().filter(x => x.logo);
            let rm = logosT.filter(x => x.logo === spec.key);
            if (!rm.length && principal && logosT.length) rm = [logosT[0]];
            const idx = rm.length ? c.getObjects().indexOf(rm[0]) : -1;
            rm.forEach(x => c.remove(x));
            const img = await loadImage(spec.src);
            const k2 = d.W / spec.W;
            // otro formato (post / historia): si el logo está en la mitad de abajo, se mantiene la distancia al borde de abajo
            let top = spec.top * k2;
            if (d.H !== spec.H && spec.cy > spec.H / 2) top = d.H - (spec.H - spec.top) * k2;
            img.set({ left: spec.left * k2, top, scaleX: spec.scaleX * k2, scaleY: spec.scaleY * k2, angle: spec.angle,
              opacity: spec.opacity, name: spec.name, logo: spec.key });
            c.add(img);
            if (idx >= 0) c.moveTo(img, idx);
            c.renderAll();
            d.fabric = c.toJSON(EXTRA);
            delete d.fabric.backgroundImage;
            const blob = await (await fetch(c.toDataURL({ format: "jpeg", quality: 0.93 }))).blob();
            c.dispose();
            await onSaveOther(d, blob);
            ok++;
          }
          hint.textContent = `Listo: el logo quedó igual en ${ok} pieza${ok > 1 ? "s" : ""} más. Tocá Guardar para esta.`;
        } catch (err) {
          hint.textContent = `Se aplicó en ${ok} de ${others.length}. Error: ${err.message || err}`;
        } finally { btn.disabled = false; }
      },
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
    root.querySelectorAll(".ed-top [data-a], .ed-foot [data-a]").forEach(b => b.onclick = () => actions[b.dataset.a]());

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
    async function setBg(color, fix = true) {
      canvas.backgroundColor = color;
      if (fix) await fixClashes(color);
      canvas.requestRenderAll(); snapshot();
      if (tab === "fondo") panel();
    }

    let toastT = null;
    function toast(t) {
      let el = root.querySelector(".ed-toast");
      if (!el) { el = document.createElement("div"); el.className = "ed-toast"; el.setAttribute("role", "status"); stage.appendChild(el); }
      el.textContent = t; el.classList.add("on");
      clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove("on"), 2800);
    }

    function onKey(e) {
      const o = active();
      const typing = (o && o.isEditing) || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
      const mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
      if (mod && k === "z" && !typing) { e.preventDefault(); actions[e.shiftKey ? "redo" : "undo"](); return; }
      if (mod && k === "y" && !typing) { e.preventDefault(); actions.redo(); return; }
      if (mod && k === "c" && !typing && o) { e.preventDefault(); copy(); return; }
      if (mod && k === "v" && !typing) { e.preventDefault(); paste(); return; }
      if (mod && k === "d" && !typing && o) { e.preventDefault(); actions.dup(); return; }
      if (mod && k === "g" && !typing && o) { e.preventDefault(); actions[e.shiftKey ? "ungroup" : "group"](); return; }
      if (mod && k === "a" && !typing) { e.preventDefault(); canvas.discardActiveObject(); const all = canvas.getObjects().filter(x => x.visible !== false && !x.bloqueado); if (all.length) canvas.setActiveObject(all.length > 1 ? new fabric.ActiveSelection(all, { canvas }) : all[0]); canvas.requestRenderAll(); return; }
      if (e.key === "Escape" && !typing) { if (o) { canvas.discardActiveObject(); canvas.requestRenderAll(); } else close(); return; }
      if (!o || typing) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); actions.del(); }
      const step = e.shiftKey ? 10 : 1;
      const mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (mv && !o.bloqueado) { e.preventDefault(); o.set({ left: o.left + mv[0], top: o.top + mv[1] }); o.setCoords(); canvas.requestRenderAll(); snapshot(); }
    }
    document.addEventListener("keydown", onKey);

    // varios cambios juntos (pegar, duplicar o borrar varios) = un solo paso de deshacer
    function batch(fn) { ed.batching = true; try { fn(); } finally { ed.batching = false; } snapshot(); }
    function snapshot() {
      if (ed.restoring || ed.batching) return;
      const st = JSON.stringify(canvas.toJSON(EXTRA));
      if (ed.history.at(-1) === st) return;
      ed.history.push(st); if (ed.history.length > 80) ed.history.shift();
      ed.future = [];
    }
    function restore(st) {
      ed.restoring = true;
      const bg = canvas.backgroundImage;
      canvas.loadFromJSON(st, () => {
        canvas.setBackgroundImage(bg, () => {});
        canvas.getObjects().forEach(o => { if (o.bloqueado) applyLock(o, true); });
        canvas.renderAll(); ed.restoring = false; panel();
      });
    }
    function close() {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", fit);
      canvas.dispose(); root.remove(); ed = null;
    }

    panel();
  }

  const logoUrl = key => "/logos/ver/" + encodeURIComponent(key).replace("%3A", ":");

  window.DEREditor = { render, open, loadFonts, build };
})();
