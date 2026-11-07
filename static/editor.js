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
  // Las piezas se diseñan en 1080 px y se entregan al doble (igual que el servidor, compose.SALIDA):
  // Fabric vuelve a dibujar textos, formas y fotos a ese tamaño, no agranda la imagen.
  const SALIDA = 2;
  const FONDOS_DER = [["liso", "Liso"], ["papel", "Papel"], ["brillo", "Brillo naranja"], ["degrade", "Degradé"], ["modulos", "Módulos DER"],
    ["patron", "Patrón DER"], ["ondas", "Ondas"], ["grilla", "Grilla de puntos"], ["rayas", "Rayas"]];
  const BRAND = { naranja: "#ff5c00", oscuro: "#333333", claro: "#f0f0f0", blanco: "#ffffff" };
  // paleta de los patrones de la marca (para las formas DER)
  const PALETA = { naranja: "#ff5c00", "naranja claro": "#f58b22", oscuro: "#333333", negro: "#1b1b1b", gris: "#8a8889", claro: "#f0f0f0" };
  // módulos de los patrones DER (caja de 100×100)
  const MODULOS = {
    cuarto: ["Cuarto de círculo", "M0 100 A100 100 0 0 1 100 0 L100 100 Z"],
    circulo: ["Círculo", "M50 0 A50 50 0 1 1 49.99 0 Z"],
    semicirculo: ["Medio círculo", "M0 75 A50 50 0 0 1 100 75 Z"],
    anillo: ["Arco", "M0 100 A100 100 0 0 1 100 0 L100 50 A50 50 0 0 0 50 100 Z"],
    triangulo: ["Triángulo", "M0 0 L100 100 L0 100 Z"],
    hoja: ["Hoja", "M0 100 A100 100 0 0 1 100 0 A100 100 0 0 1 0 100 Z"],
  };
  const DIFUMINADOS = { radial: "Brillo", abajo: "Desde abajo", arriba: "Desde arriba", lado: "Desde un lado", esquina: "Esquina", vineta: "Viñeta" };
  const FAMILIES = { title: "DER Titulo", subtitle: "DER Sub", body: "DER Cuerpo" };
  const EXTRA = ["name", "logo", "role", "bloqueado", "efecto", "curvo", "forma", "degradado", "foto", "rid"];
  if (window.fabric) fabric.filterBackend = new fabric.Canvas2dFilterBackend();  // sin límite de tamaño de textura
  const FS_MULT = 1.13; // fabric.Text._fontSizeMult
  const CLIP_KEY = "derPortapapeles";

  async function loadFonts() {
    await Promise.all(Object.values(FAMILIES).map(f => document.fonts.load(`40px "${f}"`)));
  }

  const loadImage = (url, opts = {}) =>
    new Promise((ok, fail) => fabric.Image.fromURL(url, img => img ? ok(img) : fail(url), opts));

  async function layerToObject(l, design) {
    const common = { angle: l.angle || 0, opacity: l.opacity ?? 1 };
    if (l.type === "photo") {
      // foto de la plantilla: elemento con todas las herramientas de foto (recortar, marco, filtros)
      const dir = (design.base || "").split("?")[0].replace(/\/[^/]*$/, "");
      const o = await loadImage(dir + "/" + l.src_rel, { crossOrigin: "anonymous" });
      o.set({ name: l.name || "Foto", left: l.x, top: l.y, ...common });
      o.foto = { marco: "ninguno", zoom: 1, px: 0, py: l.py || 0, filtro: l.filtro || "ninguno", aspecto: l.w / l.h, radio: l.radius || 0 };
      o.scale(l.w / (o.getElement().naturalWidth || o.width));
      applyPhoto(o);
      o.set({ left: l.x, top: l.y });
      return o;
    }
    if (l.type === "text") {
      return new fabric.Textbox(l.text, {
        left: l.x, top: l.y, width: l.w + Math.ceil(l.size * 0.15), fontFamily: l.family,
        fontSize: l.size, fill: l.color, lineHeight: l.lineGap / FS_MULT, styles: toStyles(l.styles),
        textAlign: l.align || "left", name: l.name, role: l.font, ...common,
        ...(l.stroke ? { stroke: l.stroke, strokeWidth: l.strokeWidth || 2, paintFirst: "stroke", strokeLineJoin: "round",
          efecto: String(l.color).startsWith("rgba(0,0,0,0") ? "hueco" : "contorno" } : {}),
      });
    }
    if (l.type === "rect") {
      return new fabric.Rect({ left: l.x, top: l.y, width: l.w, height: l.h, fill: l.color, name: l.name, forma: "rect",
        rx: l.rx || 0, ry: l.rx || 0, stroke: l.stroke || null, strokeWidth: l.strokeWidth || 0, ...common,
        shadow: l.shadow ? new fabric.Shadow({ color: "rgba(0,0,0,0.3)", blur: 28, offsetX: 10, offsetY: 16 }) : null,
        ...(l.gradient ? { degradado: { ...l.gradient }, fill: gradient(l.gradient) } : {}), ...(l.bloqueado ? { bloqueado: true } : {}) });
    }
    const img = await loadImage(l.src);
    img.set({ left: l.x, top: l.y, scaleX: l.w / img.width, scaleY: l.h / img.height, name: l.name, logo: l.logo || null, ...common });
    if (l.bloqueado) img.bloqueado = true;   // se aplica el candado al armar el lienzo
    return img;
  }

  function toStyles(s) {
    const out = {};
    for (const li in s || {}) { out[+li] = {}; for (const ci in s[li]) out[+li][+ci] = s[li][ci]; }
    return out;
  }

  // --- Texto curvo: se dibuja letra por letra sobre un arco (como el "Curvar" de Canva) ---------
  /** opts: {texto, family, size, fill, curva (-100..100), espaciado (px), stroke, strokeWidth, sombra}. Devuelve {url, w, h}. */
  function curvedText(o) {
    const cv = document.createElement("canvas"), ctx = cv.getContext("2d");
    const font = `${o.size}px "${o.family}"`;
    ctx.font = font;
    const chars = [...(o.texto || " ")];
    const widths = chars.map(ch => ctx.measureText(ch).width + (o.espaciado || 0));
    const total = widths.reduce((a, b) => a + b, 0) - (o.espaciado || 0);
    const ang = Math.max(0.05, Math.abs(o.curva) / 100 * Math.PI * 1.7);
    const R = Math.max(total / ang, o.size * 0.8);
    const up = o.curva >= 0, pad = o.size * 0.6 + (o.strokeWidth || 0);
    // posiciones de cada letra sobre el arco (centro del círculo en 0,0)
    let a0 = -ang / 2, acc = 0;
    const pts = chars.map((ch, i) => {
      const mid = acc + widths[i] / 2 - (o.espaciado || 0) / 2;
      acc += widths[i];
      const th = a0 + mid / R;
      return { ch, th };
    });
    const rr = up ? R : R + o.size * 0.75;
    const xs = pts.map(p => Math.sin(p.th) * rr), ys = pts.map(p => (up ? -1 : 1) * Math.cos(p.th) * rr);
    const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad - o.size * 0.4, maxY = Math.max(...ys) + pad + o.size * 0.4;
    cv.width = Math.ceil(maxX - minX); cv.height = Math.ceil(maxY - minY);
    ctx.font = font; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    if (o.sombra) { ctx.shadowColor = o.sombra.color; ctx.shadowBlur = o.sombra.blur; ctx.shadowOffsetX = o.sombra.offsetX; ctx.shadowOffsetY = o.sombra.offsetY; }
    pts.forEach((p, i) => {
      ctx.save();
      ctx.translate(xs[i] - minX, ys[i] - minY);
      ctx.rotate(up ? p.th : -p.th);
      if (o.strokeWidth) { ctx.lineWidth = o.strokeWidth * 2; ctx.strokeStyle = o.stroke; ctx.lineJoin = "round"; ctx.strokeText(p.ch, 0, up ? 0 : o.size * 0.75); }
      if (o.fill && o.fill !== "transparent") { ctx.fillStyle = o.fill; ctx.fillText(p.ch, 0, up ? 0 : o.size * 0.75); }
      ctx.restore();
    });
    return { url: cv.toDataURL("image/png"), w: cv.width, h: cv.height };
  }

  // Íconos (trazo, 24×24) para agregar como elemento
  const ICONOS = {
    estrella: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
    corazon: "M12 20s-7-4.4-9-8.6C1.6 8 3.6 5 6.8 5c2 0 3.3 1.1 4.2 2.4C11.9 6.1 13.2 5 15.2 5c3.2 0 5.2 3 3.8 6.4C19 15.6 12 20 12 20z",
    ubicacion: "M12 21s-6-5.7-6-11a6 6 0 0 1 12 0c0 5.3-6 11-6 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
    calendario: "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5",
    reloj: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
    entrada: "M3 8a2 2 0 0 0 0 4v4h18v-4a2 2 0 0 1 0-4V4H3zM14 4v12",
    micro: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
    musica: "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    check: "M4 12.5l5 5L20 6.5",
    telefono: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
    mail: "M3 6h18v12H3zM3 6l9 7 9-7",
    flecha: "M5 12h14M13 6l6 6-6 6",
    rayo: "M13 2L4 14h7l-1 8 9-12h-7z",
    persona: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21a8 8 0 0 1 16 0",
    camara: "M4 8h4l2-3h4l2 3h4v11H4zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
    copa: "M7 3h10l-1 7a4 4 0 0 1-8 0zM12 14v6M8 21h8",
  };

  // --- Fotos: filtros (como "Editar foto" de Canva), marcos y recorte ------------------------
  const FOTO_FILTROS = { ninguno: "Original", vivo: "Vivo", kodachrome: "Cálido", technicolor: "Intenso", polaroid: "Polaroid",
    vintage: "Vintage", brownie: "Sepia", bn: "Blanco y negro", bncontraste: "B/N contraste" };
  function photoFilters(fx = {}) {
    const F = fabric.Image.filters, out = [];
    const pre = { vivo: () => [new F.Vibrance({ vibrance: 0.5 }), new F.Contrast({ contrast: 0.08 })], kodachrome: () => [new F.Kodachrome()],
      technicolor: () => [new F.Technicolor()], polaroid: () => [new F.Polaroid()], vintage: () => [new F.Vintage()], brownie: () => [new F.Brownie()],
      bn: () => [new F.Grayscale()], bncontraste: () => [new F.Grayscale(), new F.Contrast({ contrast: 0.25 })] }[fx.filtro];
    if (pre) out.push(...pre());
    if (fx.brillo) out.push(new F.Brightness({ brightness: fx.brillo / 100 * 0.4 }));
    if (fx.contraste) out.push(new F.Contrast({ contrast: fx.contraste / 100 * 0.5 }));
    if (fx.saturacion) out.push(new F.Saturation({ saturation: fx.saturacion / 100 }));
    if (fx.desenfoque) out.push(new F.Blur({ blur: fx.desenfoque / 100 * 0.4 }));
    return out;
  }
  const MARCOS = { ninguno: "Sin marco", circulo: "Círculo", redondeado: "Redondeado", arco: "Arco", rombo: "Rombo" };
  function clipFor(marco, w, h) {
    const m = Math.min(w, h), common = { originX: "center", originY: "center", left: 0, top: 0 };
    if (marco === "circulo") return new fabric.Circle({ radius: m / 2, ...common });
    if (marco === "redondeado") return new fabric.Rect({ width: w, height: h, rx: m * 0.12, ry: m * 0.12, ...common });
    if (marco === "arco") return new fabric.Path(`M ${-w / 2} ${h / 2} L ${-w / 2} ${-h / 2 + w / 2} A ${w / 2} ${w / 2} 0 0 1 ${w / 2} ${-h / 2 + w / 2} L ${w / 2} ${h / 2} Z`, { ...common });
    if (marco === "rombo") return new fabric.Polygon([{ x: 0, y: -h / 2 }, { x: w / 2, y: 0 }, { x: 0, y: h / 2 }, { x: -w / 2, y: 0 }], { ...common });
    return null;
  }
  /** Aplica recorte (zoom y posición dentro del marco), marco y filtros de una foto. */
  function applyPhoto(o) {
    const f = o.foto, el = o.getElement();
    const nw = el.naturalWidth || el.width, nh = el.naturalHeight || el.height;
    const A = f.aspecto || (nw / nh);
    let cw0 = Math.min(nw, nh * A), ch0 = cw0 / A;
    const z = Math.max(1, f.zoom || 1), cw = cw0 / z, ch = ch0 / z;
    const dispW = o.getScaledWidth();
    o.set({ cropX: (nw - cw) * (0.5 + 0.5 * (f.px || 0)), cropY: (nh - ch) * (0.5 + 0.5 * (f.py || 0)), width: cw, height: ch });
    o.set({ scaleX: dispW / cw, scaleY: dispW / cw });
    o.clipPath = clipFor(f.marco, cw, ch) || (f.radio ? new fabric.Rect({ width: cw, height: ch, rx: f.radio / o.scaleX, ry: f.radio / o.scaleX,
      originX: "center", originY: "center", left: 0, top: 0 }) : undefined);
    o.objectCaching = false;   // el caché no se entera de los cambios de recorte y dejaba pedazos afuera del marco
    o.filters = photoFilters(f);
    o.applyFilters();
    o.dirty = true; o.setCoords();
  }

  /** Degradado lineal para un relleno: {a, b, ang (grados)}. */
  function gradient(g) {
    const r = (g.ang || 0) * Math.PI / 180, dx = Math.cos(r) / 2, dy = Math.sin(r) / 2;
    return new fabric.Gradient({ type: "linear", gradientUnits: "percentage",
      coords: { x1: 0.5 - dx, y1: 0.5 - dy, x2: 0.5 + dx, y2: 0.5 + dy },
      colorStops: [{ offset: 0, color: g.a }, { offset: 1, color: g.b }] });
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
      for (const l of design.layers) { const o = await layerToObject(l, design); if (l.grupo) o.grupo = l.grupo; canvas.add(o); }
      // capas con el mismo grupo (por ejemplo, la foto y su marco) = un solo elemento que se agranda junto
      const grupos = {};
      canvas.getObjects().forEach(o => { if (o.grupo) (grupos[o.grupo] = grupos[o.grupo] || []).push(o); });
      Object.entries(grupos).forEach(([nombre, objs]) => {
        if (objs.length < 2) return;
        const at = canvas.getObjects().indexOf(objs[0]);
        objs.forEach(o => { canvas.remove(o); delete o.grupo; });
        const g = new fabric.Group(objs, { name: nombre, objectCaching: false });
        canvas.add(g); canvas.moveTo(g, at);
      });
    }
    canvas.getObjects().forEach(o => { if (o.bloqueado) applyLock(o, true); if (o.foto) o.objectCaching = false; });
    // color de fondo: se ve donde la base es transparente (todo menos las fotos)
    const bgv = (design.fabric && design.fabric.background) || design.bg || BRAND.claro;
    canvas.backgroundColor = bgv && bgv.colorStops ? new fabric.Gradient(bgv) : bgv;
    const ffx = design.fabric && design.fabric.fondo_fx;
    if (ffx) { bg.filters = photoFilters(ffx); bg.applyFilters(); }
    canvas.fondoFx = ffx || null;
    canvas.renderAll();
  }

  /** Compone el diseño a resolución completa y devuelve un Blob (JPG; o PNG, con o sin fondo). */
  async function render(design, { png = false, transparente = false } = {}) {
    const el = document.createElement("canvas");
    const c = new fabric.StaticCanvas(el, { width: design.W, height: design.H, enableRetinaScaling: false });
    await build(c, design);
    if (transparente) { c.backgroundColor = null; c.renderAll(); }
    const url = png ? c.toDataURL({ format: "png", multiplier: SALIDA }) : c.toDataURL({ format: "jpeg", quality: 1, multiplier: SALIDA });
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

  function ui(navegable = false) {
    const wrap = document.createElement("div");
    wrap.className = "ed";
    wrap.innerHTML = `
      <div class="ed-stagew"><div class="ed-stage"><div class="ed-zoomwrap"><canvas></canvas></div></div>
        <div class="ed-zoombar">
          <button data-z="out" aria-label="Alejar" title="Alejar (Ctrl −)">−</button>
          <button data-z="pct" class="ed-zoomlbl" title="Tocá para ver al 100%">100%</button>
          <button data-z="in" aria-label="Acercar" title="Acercar (Ctrl +)">+</button>
          <button data-z="fit" title="Ajustar a la pantalla (Ctrl 0)">Ajustar</button>
          <button data-z="pan" class="ed-pan" title="Mover la vista con un dedo (sin tocar los elementos)" aria-label="Mover la vista">✋</button>
        </div></div>
      <aside class="ed-side">
        <div class="ed-top">
          <button data-a="undo" title="Deshacer (Ctrl+Z)" aria-label="Deshacer">${ico("undo")}</button>
          <button data-a="redo" title="Rehacer (Ctrl+Y)" aria-label="Rehacer">${ico("redo")}</button>
          <button data-a="copy" title="Copiar (Ctrl+C)" aria-label="Copiar">${ico("copy")}</button>
          <button data-a="paste" title="Pegar (Ctrl+V), también en otra pieza" aria-label="Pegar">${ico("paste")}</button>
          <span class="ed-name"></span>
          <span class="ed-nav" ${navegable ? "" : "hidden"}><button data-a="prev" aria-label="Pieza anterior" title="Guardar e ir a la anterior">‹</button><b class="ed-pg"></b><button data-a="next" aria-label="Pieza siguiente" title="Guardar e ir a la siguiente">›</button></span>
        </div>
        <div class="ed-viejo" hidden><b>Pieza de la versión anterior:</b> la foto y su marco están pegados al fondo y no se pueden mover.
          <button data-a="hacer-editable">Hacer editable ahora</button></div>
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

  async function open(design, { logos = [], patrones = [], onSave, siblings = [], onSaveOther, lote = "", onNav, onHacerEditable } = {}) {
    await loadFonts();
    const root = ui(siblings.length > 1 && !!onNav);
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

    // --- Zoom (como Canva): el lienzo crece y la zona de trabajo se desplaza -----------------
    const wrap = $(".ed-zoomwrap");
    wrap.appendChild(canvas.wrapperEl);
    let fitZ = 1, atFit = true, panMode = false;
    const dpr = window.devicePixelRatio || 1;
    // tope: que el lienzo no pase de ~4096 px reales (los celulares se quedan sin memoria)
    const maxZ = () => Math.max(fitZ * 1.5, Math.min(4, 4096 / (Math.max(design.W, design.H) * dpr)));
    function setZoomLevel(z, clientX, clientY) {
      z = Math.max(fitZ * 0.5, Math.min(maxZ(), z));
      const old = ed.zoom || z, r0 = canvas.upperCanvasEl.getBoundingClientRect();
      const fx = clientX ?? (r0.left + r0.width / 2), fy = clientY ?? (r0.top + r0.height / 2);
      const dx = (fx - r0.left) / old, dy = (fy - r0.top) / old;   // punto de la pieza bajo el puntero
      canvas.setDimensions({ width: Math.round(design.W * z), height: Math.round(design.H * z) });
      canvas.setZoom(z);
      ed.zoom = z;
      atFit = Math.abs(z - fitZ) < 0.001;
      const r1 = canvas.upperCanvasEl.getBoundingClientRect();
      stage.scrollLeft += r1.left + dx * z - fx;
      stage.scrollTop += r1.top + dy * z - fy;
      $(".ed-zoomlbl").textContent = Math.round(z * 100) + "%";
      canvas.calcOffset(); canvas.requestRenderAll();
    }
    const fit = () => {
      const r = stage.getBoundingClientRect();
      fitZ = Math.min((r.width - 24) / design.W, (r.height - 24) / design.H);
      setZoomLevel(fitZ);
      stage.scrollLeft = 0; stage.scrollTop = 0;
    };
    const onResize = () => { if (atFit) fit(); else canvas.calcOffset(); };
    fit();
    window.addEventListener("resize", onResize);
    stage.addEventListener("scroll", () => canvas.calcOffset(), { passive: true });
    root.querySelectorAll("[data-z]").forEach(b => b.onclick = () => {
      const k = b.dataset.z;
      if (k === "in") setZoomLevel(ed.zoom * 1.25);
      if (k === "out") setZoomLevel(ed.zoom / 1.25);
      if (k === "fit") fit();
      if (k === "pct") setZoomLevel(Math.min(1, maxZ()));
      if (k === "pan") {
        panMode = !panMode; b.classList.toggle("on", panMode);
        canvas.skipTargetFind = panMode; canvas.selection = !panMode;
        if (panMode) { canvas.discardActiveObject(); canvas.requestRenderAll(); }
        stage.classList.toggle("panning", panMode);
      }
    });
    // Ctrl + rueda (o pellizcar en el trackpad): zoom donde está el puntero
    stage.addEventListener("wheel", e => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      setZoomLevel(ed.zoom * Math.exp(-e.deltaY * 0.0025), e.clientX, e.clientY);
    }, { passive: false });
    // mano: arrastrar la vista con el mouse o un dedo
    let drag = null;
    stage.addEventListener("pointerdown", e => {
      if (!panMode) return;
      drag = { x: e.clientX, y: e.clientY, l: stage.scrollLeft, t: stage.scrollTop };
      stage.setPointerCapture(e.pointerId);
    });
    stage.addEventListener("pointermove", e => {
      if (!drag) return;
      stage.scrollLeft = drag.l - (e.clientX - drag.x); stage.scrollTop = drag.t - (e.clientY - drag.y);
    });
    stage.addEventListener("pointerup", () => { drag = null; });
    // dos dedos: pellizcar = zoom, arrastrar = mover la vista (sin tocar los elementos)
    let pinch = null;
    const mid = t => ({ x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2, d: Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY) });
    stage.addEventListener("touchstart", e => {
      if (e.touches.length !== 2) return;
      e.preventDefault(); e.stopPropagation();
      const m = mid(e.touches);
      pinch = { ...m, z: ed.zoom, l: stage.scrollLeft, t: stage.scrollTop };
      canvas.skipTargetFind = true;
      if (canvas._currentTransform) { canvas._currentTransform = null; }
      canvas.discardActiveObject(); canvas.requestRenderAll();
    }, { passive: false, capture: true });
    stage.addEventListener("touchmove", e => {
      if (!pinch || e.touches.length !== 2) return;
      e.preventDefault(); e.stopPropagation();
      const m = mid(e.touches);
      setZoomLevel(pinch.z * m.d / pinch.d, m.x, m.y);
      stage.scrollLeft -= m.x - (pinch.lx ?? m.x); stage.scrollTop -= m.y - (pinch.ly ?? m.y);
      pinch.lx = m.x; pinch.ly = m.y;
    }, { passive: false, capture: true });
    stage.addEventListener("touchend", e => {
      if (!pinch || e.touches.length >= 2) return;
      pinch = null; canvas.skipTargetFind = panMode;
    }, { capture: true });
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
      const shape = (k, inner, n) => `<button data-add="${k}" class="ed-card"><i class="ed-sh">${inner}</i><span>${n}</span></button>`;
      return `<h3>Textos</h3><div class="ed-grid2">
          <button data-add="texto" class="ed-card"><b class="ed-ct">Aa</b><span>Texto</span></button>
          <button data-add="titulo" class="ed-card"><b class="ed-ct t">TÍTULO</b><span>Título</span></button>
          <button data-add="combo-bajada" class="ed-card ed-combo"><b class="t">GRAN TÍTULO</b><small>con su bajada</small><span>Título + bajada</span></button>
          <button data-add="combo-cita" class="ed-card ed-combo"><b class="q">“</b><small>Una frase</small><span>Cita</span></button>
          <button data-add="combo-dato" class="ed-card ed-combo"><b class="n">+40K</b><small>asistentes</small><span>Dato</span></button>
          <button data-add="combo-etiqueta" class="ed-card ed-combo"><b class="tag">NUEVO</b><span>Etiqueta</span></button>
        </div>
        ${patrones.length ? `<h3>Patrones DER</h3><div class="ed-pats">${patrones.map(n => `<button data-add="patron:${n}" aria-label="Patrón"><img src="/patron/${n}" alt=""></button>`).join("")}</div>` : ""}
        <h3>Formas DER</h3><div class="ed-mods">${Object.entries(MODULOS).map(([k, [n, d]], i) => {
          const col = Object.values(PALETA)[i % 5];
          return `<button data-add="modulo:${k}" title="${n}" aria-label="${n}"><svg viewBox="0 0 100 100"><path d="${d}" fill="${col}"/></svg></button>`;
        }).join("")}</div>
        <p class="ed-tip" style="margin-top:4px">Con la forma elegida: girala de a 90°, cambiale el color de la paleta o duplicala para armar tu propio patrón.</p>
        <h3>Difuminados</h3><div class="ed-difs">${["#ff5c00", "#1b1b1b"].map(col => Object.entries(DIFUMINADOS).map(([k, n]) =>
          `<button data-add="dif:${k}:${col.slice(1)}" title="${n}" aria-label="Difuminado ${n}"><i class="dif-${k}" style="--c:${col}"></i><span>${n}</span></button>`).join("")).join("")}</div>
        <details class="ed-mas"><summary>Más formas</summary><div class="ed-grid4">
          ${shape("rect", `<svg viewBox="0 0 24 24"><rect x="4" y="6" width="16" height="12"/></svg>`, "Rectángulo")}
          ${shape("redondeado", `<svg viewBox="0 0 24 24"><rect x="4" y="6" width="16" height="12" rx="4"/></svg>`, "Redondeado")}
          ${shape("circulo", `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/></svg>`, "Círculo")}
          ${shape("linea", `<svg viewBox="0 0 24 24"><path d="M3 12h18" class="st"/></svg>`, "Línea")}
          ${shape("flecha", `<svg viewBox="0 0 24 24"><path d="${ICONOS.flecha}" class="st"/></svg>`, "Flecha")}
          ${shape("barra", `<i class="ed-cbar"></i>`, "Barra")}
        </div></details>
        <h3>Fotos</h3><div class="ed-grid2">
          <button data-a="subir-foto" class="ed-card"><i class="ed-cfoto"></i><span>Subir foto</span></button>
          <button data-a="foto-fondo" class="ed-card"><i class="ed-cfoto f"></i><span>Foto de fondo</span></button>
        </div>
        <h3>Marca</h3><div class="ed-grid2">
          <button data-add="esquinero" class="ed-card"><i class="ed-ccor"></i><span>Esquinero</span></button>
          <button data-add="puntos" class="ed-card"><i class="ed-cdots"></i><span>Puntos</span></button>
        </div>
        <label>Logo</label><select class="ed-addlogo"><option value="">+ Agregar logo…</option>${logoOptsHtml("")}</select>
        <p class="ed-tip">Tocá un elemento para editarlo. Para elegir varios: arrastrá un recuadro, Shift + clic, o el botón <b>Elegir varios</b>.</p>
        <button class="ed-wide ${multi ? "on" : ""}" data-a="multi">${multi ? "✓ Elegir varios activado" : "Elegir varios"}</button>`;
    }

    // fondos de marca (brillo, degradé, módulos…): capas bloqueadas al fondo de todo, se reemplazan entre sí
    async function ponerFondoDer(kind) {
      const bg = typeof canvas.backgroundColor === "string" ? canvas.backgroundColor : "#333333";
      const r = await fetch(`/api/fondo-capas?fondo=${kind}&W=${design.W}&H=${design.H}&bg=${encodeURIComponent(bg)}`);
      if (!r.ok) return toast("No se pudo cargar ese fondo.");
      const { capas, prefijo } = await r.json();
      canvas.getObjects().filter(o => (o.name || "").startsWith(prefijo) || (o.name === "Textura" && o.bloqueado)).forEach(o => canvas.remove(o));
      let i = 0;
      for (const l of capas) {
        const o = await layerToObject(l, design);
        canvas.add(o); canvas.moveTo(o, i++);
        if (o.bloqueado) applyLock(o, true);
      }
      canvas.requestRenderAll(); snapshot();
    }

    function fondoHTML() {
      const bg = typeof canvas.backgroundColor === "string" ? canvas.backgroundColor.toLowerCase() : "";
      const tono = (() => { const m = /^#?([0-9a-f]{6})$/i.exec(bg); if (!m) return "oscuro"; const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
        if (r > 200 && g > 60 && g < 150 && b < 90) return "naranja"; return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "claro" : "oscuro"; })();
      return `<h3>Fondos DER</h3><div class="ed-fondos">${FONDOS_DER.map(([k, n]) => `<button data-fder="${k}" title="${n}">
          ${k === "liso" ? `<i style="background:${bg || "#333"}"></i>` : `<img src="/fondo-muestra/${k}.jpg?tono=${tono}" alt="" loading="lazy">`}<span>${n}</span></button>`).join("")}</div>
        <p class="ed-tip">Se adapta al color de fondo de la pieza: cambiá primero el color y después elegí el fondo.</p>
        <label>Color de fondo</label><div class="ed-sw ed-bg">
          ${Object.entries(BRAND).map(([k, v]) => `<button data-bg="${v}" title="Fondo ${k}" class="${bg === v ? "on" : ""}" style="background:${v}"></button>`).join("")}
          <label class="ed-otro" title="Otro color"><input type="color" data-bgpick value="${/^#[0-9a-f]{6}$/i.test(bg) ? bg : "#333333"}"><span>Otro</span></label>
        </div><p class="ed-tip">Cambia el fondo liso de la pieza (las fotos no se tocan). Lo que queda del mismo color que el fondo pasa solo a un color que contraste.</p>
        <h3>Degradado de fondo</h3>
        <div class="ed-gradbg">${[[BRAND.naranja, BRAND.oscuro], [BRAND.oscuro, "#000000"], [BRAND.naranja, "#ffb380"], [BRAND.claro, BRAND.blanco], ["#333333", BRAND.naranja]].map(([a, b]) =>
          `<button data-bggrad="${a},${b}" style="background:linear-gradient(135deg,${a},${b})" aria-label="Degradado"></button>`).join("")}</div>
        <label>Ángulo <output>${bgAng}°</output></label><input type="range" data-bgang min="0" max="360" step="15" value="${bgAng}">
        <h3>Foto de fondo de la plantilla</h3>
        <div class="ed-fl">${Object.entries(FOTO_FILTROS).map(([k, n]) => `<button data-ffx="${k}" class="${(fondoFx().filtro || "ninguno") === k ? "on" : ""}">${n}</button>`).join("")}</div>
        <label>Brillo <output>${fondoFx().brillo || 0}</output></label><input type="range" data-ffa="brillo" min="-100" max="100" value="${fondoFx().brillo || 0}">
        <label>Contraste <output>${fondoFx().contraste || 0}</output></label><input type="range" data-ffa="contraste" min="-100" max="100" value="${fondoFx().contraste || 0}">
        <label>Saturación <output>${fondoFx().saturacion || 0}</output></label><input type="range" data-ffa="saturacion" min="-100" max="100" value="${fondoFx().saturacion || 0}">
        <p class="ed-tip">Afecta toda la imagen de base de la plantilla (foto, degradés y bandas).</p>`;
    }
    let bgAng = 135, bgGrad = null;
    const fondoFx = () => canvas.fondoFx || {};

    const kindName = o => o.type === "activeSelection" ? `${o.getObjects().length} elementos` :
      o.name || (o.type === "group" ? "Grupo" : o.type === "textbox" ? "Texto" : o.logo ? "Logo" : "Elemento");

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
      if (o.curvo) h += curvoHTML(o);
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
          </div>
          <div class="ed-btns ed-biu">
            <button data-a="bold" class="${o.fontWeight === "bold" ? "on" : ""}" title="Negrita"><b>B</b></button>
            <button data-a="italic" class="${o.fontStyle === "italic" ? "on" : ""}" title="Cursiva"><i>I</i></button>
            <button data-a="underline" class="${o.underline ? "on" : ""}" title="Subrayado"><u>U</u></button>
          </div>
          <label>Espaciado de letras <output>${Math.round(o.charSpacing || 0)}</output></label><input type="range" data-p="charSpacing" min="-100" max="800" step="10" value="${o.charSpacing || 0}">
          <label>Interlineado <output>${(o.lineHeight || 1).toFixed(2)}</output></label><input type="range" data-p="lineHeight" min="0.6" max="2.2" step="0.02" value="${o.lineHeight || 1}">
          ${efectosHTML(o)}`;
      }
      if (isShape(o)) h += formaHTML(o);
      if (isLogo) h += `<label>Cambiar logo</label><select data-p="logo">${logoOptsHtml(o.logo)}</select>`;
      if (o.foto) h += fotoHTML(o);
      if (!isSel && siblings.length > 1) h += `<button data-a="replicar" class="ed-wide ed-replicar">${isLogo ? "Replicar el logo" : "Aplicar"} en todas las piezas</button>
          <p class="ed-rep-hint">Mismo elemento, tamaño y lugar en el resto de las piezas de este lote (si ya estaba, se reemplaza).</p>`;
      if (!isLogo && !o.curvo && !(isShape(o) && o.degradado)) {
        h += `<label>${isShape(o) && !isStroke(o) ? "Relleno" : "Color"} <small class="ed-colorhint"></small></label><div class="ed-sw">
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

    const isShape = o => !!o.forma;
    const isStroke = o => ["linea", "flecha", "icono"].includes(o.forma);
    const dots = (attr, cur) => Object.entries(BRAND).map(([k, v]) => `<button ${attr}="${v}" title="${k}" class="${(cur || "").toLowerCase() === v ? "on" : ""}" style="background:${v}"></button>`).join("");

    function efectosHTML(o) {
      const e = o.efecto || "ninguno", fs = o.fontSize;
      const ef = { ninguno: "Ninguno", sombra: "Sombra", contorno: "Contorno", hueco: "Hueco", neon: "Neón", resaltado: "Resaltado", curvo: "Curvo" };
      let h = `<h3>Efectos</h3><div class="ed-fx">${Object.entries(ef).map(([k, n]) => `<button data-fx="${k}" class="${e === k ? "on" : ""}"><i class="fx-${k}">Aa</i><span>${n}</span></button>`).join("")}</div>`;
      if (e === "sombra" && o.shadow) h += `<label>Desenfoque <output>${Math.round(o.shadow.blur)}</output></label><input type="range" data-fxp="blur" min="0" max="${Math.round(fs)}" value="${o.shadow.blur}">
        <label>Distancia <output>${Math.round(o.shadow.offsetY)}</output></label><input type="range" data-fxp="dist" min="0" max="${Math.round(fs * 0.5)}" value="${o.shadow.offsetY}">
        <label>Color de la sombra</label><div class="ed-sw">${dots("data-fxc", o.shadow.color)}<button data-fxc="rgba(0,0,0,0.55)" title="negro suave" style="background:rgba(0,0,0,.55)"></button></div>`;
      if ((e === "contorno" || e === "hueco") && o.stroke) h += `<label>Grosor <output>${Math.round(o.strokeWidth)}</output></label><input type="range" data-fxp="stroke" min="1" max="${Math.round(fs * 0.25)}" value="${o.strokeWidth}">
        <label>Color del contorno</label><div class="ed-sw">${dots("data-fxc", o.stroke)}</div>`;
      if (e === "neon" && o.shadow) h += `<label>Intensidad <output>${Math.round(o.shadow.blur)}</output></label><input type="range" data-fxp="blur" min="4" max="${Math.round(fs * 1.5)}" value="${o.shadow.blur}">
        <label>Color del brillo</label><div class="ed-sw">${dots("data-fxc", o.shadow.color)}</div>`;
      if (e === "resaltado") h += `<label>Color del resaltado</label><div class="ed-sw">${dots("data-fxc", o.textBackgroundColor)}</div>`;
      return h;
    }

    function fotoHTML(o) {
      const f = o.foto;
      return `<div class="ed-btns"><button data-a="reemplazar-foto">Reemplazar foto</button></div>
        <h3>Marco</h3><div class="ed-btns">${Object.entries(MARCOS).map(([k, n]) => `<button data-marco="${k}" class="${(f.marco || "ninguno") === k ? "on" : ""}">${n}</button>`).join("")}</div>
        <h3>Recortar</h3>
        <label>Zoom <output>${(f.zoom || 1).toFixed(2)}x</output></label><input type="range" data-ph="zoom" min="1" max="4" step="0.05" value="${f.zoom || 1}">
        <label>Mover ← → <output>${Math.round((f.px || 0) * 100)}</output></label><input type="range" data-ph="px" min="-1" max="1" step="0.02" value="${f.px || 0}">
        <label>Mover ↑ ↓ <output>${Math.round((f.py || 0) * 100)}</output></label><input type="range" data-ph="py" min="-1" max="1" step="0.02" value="${f.py || 0}">
        <label>Forma del recorte</label><div class="ed-btns">${[["", "Original"], ["1", "1:1"], ["0.8", "4:5"], ["0.5625", "9:16"], ["1.7778", "16:9"]].map(([v, n]) => `<button data-asp="${v}" class="${String(f.aspecto || "") === v ? "on" : ""}">${n}</button>`).join("")}</div>
        <h3>Filtros</h3><div class="ed-fl">${Object.entries(FOTO_FILTROS).map(([k, n]) => `<button data-pf="${k}" class="${(f.filtro || "ninguno") === k ? "on" : ""}">${n}</button>`).join("")}</div>
        <h3>Ajustes</h3>
        ${[["brillo", "Brillo"], ["contraste", "Contraste"], ["saturacion", "Saturación"], ["desenfoque", "Desenfoque"]].map(([k, n]) =>
          `<label>${n} <output>${f[k] || 0}</output></label><input type="range" data-ph="${k}" min="${k === "desenfoque" ? 0 : -100}" max="100" value="${f[k] || 0}">`).join("")}`;
    }

    function curvoHTML(o) {
      const c = o.curvo;
      return `<label>Texto</label><input type="text" class="ed-in" data-cv="texto" value="${esc(c.texto)}">
        <label>Curvatura <output>${c.curva}</output></label><input type="range" data-cv="curva" min="-100" max="100" step="1" value="${c.curva}">
        <label>Tamaño <output>${Math.round(c.size)} px</output></label><input type="range" data-cv="size" min="12" max="300" value="${c.size}">
        <label>Espaciado de letras <output>${Math.round(c.espaciado || 0)}</output></label><input type="range" data-cv="espaciado" min="-10" max="80" value="${c.espaciado || 0}">
        <label>Tipografía</label><select data-cv="role"><option value="title" ${c.role === "title" ? "selected" : ""}>Títulos (Netron)</option>
          <option value="subtitle" ${c.role === "subtitle" ? "selected" : ""}>Subtítulos</option><option value="body" ${c.role === "body" ? "selected" : ""}>Texto (Jost)</option></select>
        <label>Color</label><div class="ed-sw">${dots("data-cvc", c.fill)}</div>
        <button class="ed-wide sec" data-a="uncurve">Quitar la curva (volver a texto normal)</button>`;
    }

    function formaHTML(o) {
      let h = "";
      if (o.forma === "modulo") h += `<h3>Forma DER</h3><div class="ed-btns"><button data-a="rot90l">⟲ 90°</button><button data-a="rot90r">⟳ 90°</button>
        <button data-a="fliph">Espejar ⇆</button></div>
        <label>Color de la paleta</label><div class="ed-sw">${Object.entries(PALETA).map(([n, v]) => `<button data-color="${v}" title="${n}" style="background:${v}"></button>`).join("")}</div>`;
      if (!isStroke(o)) {
        const g = o.degradado;
        h += `<h3>Relleno</h3><div class="ed-btns"><button data-fill="solido" class="${g ? "" : "on"}">Sólido</button><button data-fill="degradado" class="${g ? "on" : ""}">Degradado</button></div>`;
        if (g) h += `<label>Color 1</label><div class="ed-sw">${dots("data-ga", g.a)}<label class="ed-otro"><input type="color" data-gpick="a" value="${g.a}"></label></div>
          <label>Color 2</label><div class="ed-sw">${dots("data-gb", g.b)}<label class="ed-otro"><input type="color" data-gpick="b" value="${g.b}"></label></div>
          <label>Ángulo <output>${g.ang}°</output></label><input type="range" data-gang min="0" max="360" step="15" value="${g.ang}">`;
      }
      const sw = o.strokeWidth || 0;
      h += `<h3>${isStroke(o) ? "Trazo" : "Borde"}</h3>
        <label>Grosor <output>${Math.round(sw)}</output></label><input type="range" data-shp="strokeWidth" min="${isStroke(o) ? 1 : 0}" max="60" value="${sw}">
        ${!isStroke(o) ? `<label>Color del borde</label><div class="ed-sw">${dots("data-shc", o.stroke)}</div>` : ""}`;
      if (o.type === "rect") h += `<label>Esquinas redondeadas <output>${Math.round(o.rx || 0)}</output></label><input type="range" data-shp="rx" min="0" max="${Math.round(Math.min(o.width, o.height) / 2)}" value="${o.rx || 0}">`;
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
      // estilo de texto
      ["charSpacing", "lineHeight"].forEach(k => {
        const r = P.querySelector(`[data-p=${k}]`);
        if (!r) return;
        r.oninput = () => { o.set(k, +r.value); o.initDimensions(); r.previousElementSibling.querySelector("output").textContent = k === "lineHeight" ? (+r.value).toFixed(2) : r.value; canvas.requestRenderAll(); };
        r.onchange = () => snapshot();
      });
      P.querySelectorAll("[data-fx]").forEach(b => b.onclick = () => setEffect(o, b.dataset.fx));
      P.querySelectorAll("[data-fxp]").forEach(r => {
        r.oninput = () => {
          const v = +r.value, k = r.dataset.fxp;
          if (k === "blur") o.shadow.blur = v;
          if (k === "dist") { o.shadow.offsetY = v; o.shadow.offsetX = v * 0.6; }
          if (k === "stroke") o.set("strokeWidth", v);
          r.previousElementSibling.querySelector("output").textContent = Math.round(v);
          o.dirty = true; canvas.requestRenderAll();
        };
        r.onchange = () => snapshot();
      });
      P.querySelectorAll("[data-fxc]").forEach(b => b.onclick = () => {
        const c = b.dataset.fxc, e = o.efecto;
        if (e === "sombra" || e === "neon") o.shadow.color = c;
        if (e === "contorno" || e === "hueco") o.set("stroke", c);
        if (e === "resaltado") o.set("textBackgroundColor", c);
        o.dirty = true; canvas.requestRenderAll(); snapshot(); panel();
      });
      // texto curvo
      P.querySelectorAll("[data-cv]").forEach(el => {
        const k = el.dataset.cv;
        const upd = () => { o.curvo[k] = el.type === "range" ? +el.value : el.value; if (k === "role") o.curvo.family = FAMILIES[el.value]; redrawCurve(o); };
        if (el.type === "range") { el.oninput = () => { el.previousElementSibling.querySelector("output").textContent = el.value + (k === "size" ? " px" : ""); upd(); }; el.onchange = () => snapshot(); }
        else { el.oninput = el.tagName === "SELECT" ? null : upd; el.onchange = () => { upd(); snapshot(); }; }
      });
      P.querySelectorAll("[data-cvc]").forEach(b => b.onclick = () => { o.curvo.fill = b.dataset.cvc; redrawCurve(o).then(() => { snapshot(); panel(); }); });
      // formas
      P.querySelectorAll("[data-fill]").forEach(b => b.onclick = () => {
        if (b.dataset.fill === "degradado") { const base = typeof o.fill === "string" ? o.fill : BRAND.naranja; o.degradado = { a: base, b: BRAND.oscuro, ang: 90 }; o.set("fill", gradient(o.degradado)); }
        else { const c = o.degradado ? o.degradado.a : BRAND.naranja; o.degradado = null; o.set("fill", c); }
        canvas.requestRenderAll(); snapshot(); panel();
      });
      const setG = (k, v) => { o.degradado[k] = v; o.set("fill", gradient(o.degradado)); o.dirty = true; canvas.requestRenderAll(); };
      P.querySelectorAll("[data-ga]").forEach(b => b.onclick = () => { setG("a", b.dataset.ga); snapshot(); panel(); });
      P.querySelectorAll("[data-gb]").forEach(b => b.onclick = () => { setG("b", b.dataset.gb); snapshot(); panel(); });
      P.querySelectorAll("[data-gpick]").forEach(i => i.onchange = () => { setG(i.dataset.gpick, i.value); snapshot(); panel(); });
      const ga = P.querySelector("[data-gang]");
      if (ga) { ga.oninput = () => { setG("ang", +ga.value); ga.previousElementSibling.querySelector("output").textContent = ga.value + "°"; }; ga.onchange = () => snapshot(); }
      P.querySelectorAll("[data-shp]").forEach(r => {
        r.oninput = () => {
          const k = r.dataset.shp, v = +r.value;
          if (k === "rx") o.set({ rx: v, ry: v }); else { o.set(k, v); if (!o.stroke && v > 0) o.set("stroke", BRAND.oscuro); }
          r.previousElementSibling.querySelector("output").textContent = Math.round(v);
          canvas.requestRenderAll();
        };
        r.onchange = () => { snapshot(); if (r.dataset.shp === "strokeWidth") panel(); };
      });
      P.querySelectorAll("[data-shc]").forEach(b => b.onclick = () => { o.set("stroke", b.dataset.shc); if (!o.strokeWidth) o.set("strokeWidth", 6 * s); canvas.requestRenderAll(); snapshot(); panel(); });
      // foto: marco, recorte, filtros, ajustes
      P.querySelectorAll("[data-marco]").forEach(b => b.onclick = () => { o.foto.marco = b.dataset.marco; applyPhoto(o); canvas.requestRenderAll(); snapshot(); panel(); });
      P.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => { o.foto.filtro = b.dataset.pf; applyPhoto(o); canvas.requestRenderAll(); snapshot(); panel(); });
      P.querySelectorAll("[data-asp]").forEach(b => b.onclick = () => { o.foto.aspecto = b.dataset.asp ? +b.dataset.asp : null; applyPhoto(o); canvas.requestRenderAll(); snapshot(); panel(); });
      P.querySelectorAll("[data-ph]").forEach(r => {
        const k = r.dataset.ph, light = ["zoom", "px", "py"].includes(k);
        r.oninput = () => {
          o.foto[k] = +r.value;
          r.previousElementSibling.querySelector("output").textContent = k === "zoom" ? (+r.value).toFixed(2) + "x" : light ? Math.round(r.value * 100) : r.value;
          if (light) applyPhoto(o); canvas.requestRenderAll();
        };
        r.onchange = () => { if (!light) applyPhoto(o); canvas.requestRenderAll(); snapshot(); };
      });
      P.querySelectorAll("[data-fder]").forEach(b => b.onclick = () => ponerFondoDer(b.dataset.fder));
      // fondo: degradado y foto de base
      P.querySelectorAll("[data-bggrad]").forEach(b => b.onclick = () => { const [a, c] = b.dataset.bggrad.split(","); bgGrad = { a, b: c }; setBgGradient(); });
      const ba = P.querySelector("[data-bgang]");
      if (ba) { ba.oninput = () => { bgAng = +ba.value; ba.previousElementSibling.querySelector("output").textContent = ba.value + "°"; if (bgGrad) setBgGradient(false); }; ba.onchange = () => snapshot(); }
      P.querySelectorAll("[data-ffx]").forEach(b => b.onclick = () => { canvas.fondoFx = { ...fondoFx(), filtro: b.dataset.ffx }; applyFondo(); panel(); });
      P.querySelectorAll("[data-ffa]").forEach(r => {
        r.oninput = () => { r.previousElementSibling.querySelector("output").textContent = r.value; };
        r.onchange = () => { canvas.fondoFx = { ...fondoFx(), [r.dataset.ffa]: +r.value }; applyFondo(); };
      });
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
        } else if (isStroke(t)) t.set("stroke", color);
        else if (t.forma || t.type === "rect" || t.type === "circle" || t.type === "path" || t.type === "polygon" || t.type === "triangle") { t.degradado = null; t.set("fill", color); }
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

    function setEffect(o, fx) {
      if (fx === "curvo") return curve(o);
      const fs = o.fontSize, keepFill = o.efecto === "hueco" || o.efecto === "neon" ? (o._fillPrev || BRAND.blanco) : o.fill;
      o.set({ shadow: null, stroke: null, strokeWidth: 0, textBackgroundColor: "", paintFirst: "fill", fill: keepFill });
      if (fx === "sombra") o.set("shadow", new fabric.Shadow({ color: "rgba(0,0,0,0.55)", blur: fs * 0.18, offsetX: fs * 0.05, offsetY: fs * 0.08 }));
      if (fx === "contorno") o.set({ stroke: BRAND.naranja, strokeWidth: Math.max(2, fs * 0.06), paintFirst: "stroke", strokeLineJoin: "round" });
      if (fx === "hueco") { o._fillPrev = keepFill; o.set({ fill: "rgba(0,0,0,0)", stroke: typeof keepFill === "string" ? keepFill : BRAND.blanco, strokeWidth: Math.max(2, fs * 0.04), strokeLineJoin: "round" }); }
      if (fx === "neon") { o._fillPrev = keepFill; o.set({ fill: "#fff7f0", shadow: new fabric.Shadow({ color: BRAND.naranja, blur: fs * 0.55, offsetX: 0, offsetY: 0 }) }); }
      if (fx === "resaltado") o.set({ textBackgroundColor: BRAND.naranja });
      o.efecto = fx === "ninguno" ? null : fx;
      o.styles = o.styles || {};
      o.dirty = true; canvas.requestRenderAll(); snapshot(); panel();
    }

    // Curvar: el texto pasa a ser una imagen que se vuelve a dibujar con cada cambio
    async function curve(t) {
      const c = { texto: t.text.replace(/\n/g, " "), family: t.fontFamily, role: t.role || "subtitle", size: t.fontSize, fill: typeof t.fill === "string" ? t.fill : BRAND.blanco,
        curva: 45, espaciado: (t.charSpacing || 0) / 1000 * t.fontSize, original: t.toObject(EXTRA) };
      const img = await makeCurve(c);
      const cx = t.getCenterPoint();
      img.set({ angle: t.angle, opacity: t.opacity, name: "Texto curvo" });
      img.setPositionByOrigin(cx, "center", "center");
      const i = canvas.getObjects().indexOf(t);
      batch(() => { canvas.remove(t); canvas.add(img); canvas.moveTo(img, i); });
      canvas.setActiveObject(img); canvas.requestRenderAll(); snapshot(); panel();
    }
    async function makeCurve(c) {
      const r = curvedText(c);
      const img = await loadImage(r.url);
      img.curvo = c;
      return img;
    }
    async function redrawCurve(o) {
      const center = o.getCenterPoint(), r = curvedText(o.curvo);
      await new Promise(ok => o.setSrc(r.url, ok));
      o.set({ scaleX: 1, scaleY: 1 });
      o.setPositionByOrigin(center, "center", "center"); o.setCoords();
      canvas.requestRenderAll();
    }
    async function uncurve() {
      const o = active();
      if (!o || !o.curvo) return;
      const c = o.curvo;
      const [t] = await new Promise(ok => fabric.util.enlivenObjects([{ ...c.original, text: c.texto, fill: c.fill, fontSize: c.size, fontFamily: c.family, role: c.role }], ok));
      t.efecto = null;
      t.setPositionByOrigin(o.getCenterPoint(), "center", "center");
      const i = canvas.getObjects().indexOf(o);
      batch(() => { canvas.remove(o); canvas.add(t); canvas.moveTo(t, i); });
      canvas.setActiveObject(t); canvas.requestRenderAll(); snapshot(); panel();
    }

    function setBgGradient(snap = true) {
      const r = bgAng * Math.PI / 180, cx = design.W / 2, cy = design.H / 2, L = Math.hypot(design.W, design.H) / 2;
      canvas.backgroundColor = new fabric.Gradient({ type: "linear", gradientUnits: "pixels",
        coords: { x1: cx - Math.cos(r) * L, y1: cy - Math.sin(r) * L, x2: cx + Math.cos(r) * L, y2: cy + Math.sin(r) * L },
        colorStops: [{ offset: 0, color: bgGrad.a }, { offset: 1, color: bgGrad.b }] });
      canvas.requestRenderAll(); if (snap) snapshot();
    }
    function applyFondo() {
      const bg = canvas.backgroundImage;
      if (!bg) return;
      bg.filters = photoFilters(canvas.fondoFx || {}); bg.applyFilters();
      canvas.requestRenderAll();
    }

    // fotos subidas desde el celular o la compu
    function pickPhoto() {
      return new Promise(ok => {
        const inp = document.createElement("input");
        inp.type = "file"; inp.accept = "image/*";
        inp.onchange = async () => {
          const f = inp.files[0];
          if (!f) return ok(null);
          toast("Subiendo la foto…");
          const fd = new FormData(); fd.append("lote", lote); fd.append("archivo", f);
          try {
            const r = await fetch("/api/pieza/medio", { method: "POST", body: fd }), j = await r.json();
            if (!r.ok) throw new Error(j.error);
            ok(j.url);
          } catch (err) { toast("No se pudo subir: " + err.message); ok(null); }
        };
        inp.click();
      });
    }
    async function addPhoto(asBackground) {
      const url = await pickPhoto();
      if (!url) return;
      const o = await loadImage(url, { crossOrigin: "anonymous" });
      o.set({ name: asBackground ? "Foto de fondo" : "Foto" });
      o.foto = { marco: "ninguno", zoom: 1, px: 0, py: 0, filtro: "ninguno", aspecto: asBackground ? design.W / design.H : null };
      if (asBackground) {
        o.scale(design.W / o.width);
        applyPhoto(o);
        o.set({ left: 0, top: 0 });
        canvas.add(o); o.sendToBack(); applyLock(o, true);
      } else {
        o.scale(design.W * 0.6 / o.width);
        applyPhoto(o);
        canvas.add(center(o));
      }
      canvas.setActiveObject(o); canvas.requestRenderAll(); snapshot(); panel();
    }
    async function replacePhoto() {
      const o = active();
      const url = await pickPhoto();
      if (!url || !o) return;
      const w = o.getScaledWidth();
      await new Promise(ok => o.setSrc(url, ok, { crossOrigin: "anonymous" }));
      o.set({ scaleX: w / o.width, scaleY: w / o.width });
      applyPhoto(o); canvas.requestRenderAll(); snapshot(); panel();
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
      const S = 300 * s;
      if (k === "rect") o = new fabric.Rect({ width: S, height: S * 0.7, fill: BRAND.naranja, name: "Rectángulo", forma: "rect" });
      if (k === "redondeado") o = new fabric.Rect({ width: S, height: S * 0.7, rx: 40 * s, ry: 40 * s, fill: BRAND.naranja, name: "Rectángulo redondeado", forma: "rect" });
      if (k === "circulo") o = new fabric.Circle({ radius: S / 2, fill: BRAND.naranja, name: "Círculo", forma: "circulo" });
      if (k === "triangulo") o = new fabric.Triangle({ width: S, height: S * 0.87, fill: BRAND.naranja, name: "Triángulo", forma: "triangulo" });
      if (k === "estrella5") { o = new fabric.Path(ICONOS.estrella, { fill: BRAND.naranja, name: "Estrella", forma: "estrella" }); o.scale(S / 18); }
      if (k === "linea") o = new fabric.Line([0, 0, S * 1.3, 0], { stroke: BRAND.naranja, strokeWidth: 8 * s, strokeLineCap: "round", name: "Línea", forma: "linea" });
      if (k === "flecha") { o = new fabric.Path("M2 12h20M15 5l7 7-7 7", { fill: "", stroke: BRAND.naranja, strokeWidth: 2.2, strokeLineCap: "round", strokeLineJoin: "round", name: "Flecha", forma: "flecha" }); o.scale(S / 22); }
      if (k.startsWith("icono:")) {
        const n = k.slice(6);
        o = new fabric.Path(ICONOS[n], { fill: "", stroke: BRAND.naranja, strokeWidth: 1.8, strokeLineCap: "round", strokeLineJoin: "round", name: "Ícono " + n, forma: "icono" });
        o.scale(160 * s / 24);
      }
      if (k.startsWith("combo-")) return addCombo(k.slice(6));
      if (k.startsWith("patron:")) {
        o = await loadImage("/patron/" + k.slice(7));
        o.set({ name: "Patrón DER", left: 0, top: 0 }); o.scale(design.W / o.width);
        canvas.add(o); canvas.setActiveObject(o); canvas.requestRenderAll(); return;
      }
      if (k.startsWith("modulo:")) {
        const [, key] = k.split(":");
        o = new fabric.Path(MODULOS[key][1], { fill: PALETA.naranja, name: MODULOS[key][0], forma: "modulo" });
        o.scale(240 * s / 100);
      }
      if (k.startsWith("dif:")) {
        const [, forma, col] = k.split(":");
        const size = { radial: [0.9, 0.9 * design.W / design.H], abajo: [1, 0.55], arriba: [1, 0.55], lado: [0.6, 1], esquina: [0.9, 0.75], vineta: [1, 1] }[forma];
        const w = Math.round(design.W * size[0]), h = Math.round(design.H * size[1]);
        o = await loadImage(`/elemento/difuminado.png?forma=${forma}&w=${Math.round(w / 2)}&h=${Math.round(h / 2)}&color=${col}`);
        o.set({ name: "Difuminado", scaleX: w / o.width, scaleY: h / o.height });
        const pos = { abajo: [0, design.H - h], arriba: [0, 0], lado: [0, 0], esquina: [0, design.H - h], vineta: [0, 0] }[forma];
        if (pos) { o.set({ left: pos[0], top: pos[1] }); canvas.add(o); }
        else canvas.add(center(o));
        canvas.setActiveObject(o); canvas.requestRenderAll(); return;
      }
      if (!o) return;
      canvas.add(center(o)); canvas.setActiveObject(o); canvas.requestRenderAll();
    }

    // Combinaciones de texto prediseñadas (quedan elegidas juntas; se editan por separado)
    function addCombo(kind) {
      const T = (txt, o) => new fabric.Textbox(txt, { fill: BRAND.blanco, textAlign: "center", ...o });
      let objs = [];
      if (kind === "bajada") objs = [
        T("GRAN TÍTULO", { width: 860 * s, fontFamily: FAMILIES.title, role: "title", fontSize: 120 * s, name: "Título", top: 0 }),
        new fabric.Rect({ width: 90 * s, height: 10 * s, fill: BRAND.naranja, name: "Barra", left: 385 * s, top: 150 * s }),
        T("Una bajada corta que explica", { width: 860 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 48 * s, name: "Bajada", top: 185 * s })];
      if (kind === "cita") objs = [
        T("“", { width: 200 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 260 * s, fill: BRAND.naranja, name: "Comillas", left: 330 * s, top: 0 }),
        T("La producción buena es la que nadie nota", { width: 800 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 64 * s, name: "Frase", top: 200 * s }),
        T("— NOMBRE, CARGO", { width: 800 * s, fontFamily: FAMILIES.body, role: "body", fontSize: 32 * s, name: "Firma", top: 380 * s, charSpacing: 120 })];
      if (kind === "dato") objs = [
        T("+40K", { width: 800 * s, fontFamily: FAMILIES.title, role: "title", fontSize: 240 * s, fill: BRAND.naranja, name: "Número", top: 0 }),
        T("asistentes en 3 días", { width: 800 * s, fontFamily: FAMILIES.subtitle, role: "subtitle", fontSize: 56 * s, name: "Qué es", top: 260 * s })];
      if (kind === "etiqueta") objs = [
        T(" NUEVO ", { width: 360 * s, fontFamily: FAMILIES.title, role: "title", fontSize: 56 * s, name: "Etiqueta", textBackgroundColor: BRAND.naranja, efecto: "resaltado", top: 0 })];
      // ubicar el conjunto centrado en la pieza
      const minL = Math.min(...objs.map(o => o.left || 0)), maxW = Math.max(...objs.map(o => (o.left || 0) + o.getScaledWidth()));
      const maxH = Math.max(...objs.map(o => (o.top || 0) + o.getScaledHeight()));
      const dx = (design.W - (maxW - minL)) / 2 - minL, dy = (design.H - maxH) / 2;
      batch(() => objs.forEach(o => { o.set({ left: (o.left || 0) + dx, top: (o.top || 0) + dy }); canvas.add(o); }));
      canvas.discardActiveObject();
      canvas.setActiveObject(objs.length > 1 ? new fabric.ActiveSelection(objs, { canvas }) : objs[0]);
      canvas.requestRenderAll(); panel();
    }

    // --- copiar estilo (brocha) ---------------------------------------------------------
    const STYLE_KEYS = ["fill", "fontFamily", "role", "fontSize", "fontWeight", "fontStyle", "underline", "textAlign", "lineHeight",
      "charSpacing", "stroke", "strokeWidth", "shadow", "opacity", "rx", "ry", "textBackgroundColor", "efecto", "paintFirst", "strokeLineJoin"];
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
      rot90l() { const o = active(); o.rotate(((o.angle || 0) + 270) % 360); o.setCoords(); canvas.requestRenderAll(); snapshot(); },
      rot90r() { const o = active(); o.rotate(((o.angle || 0) + 90) % 360); o.setCoords(); canvas.requestRenderAll(); snapshot(); },
      bold() { const o = active(); o.set("fontWeight", o.fontWeight === "bold" ? "normal" : "bold"); o.initDimensions(); canvas.requestRenderAll(); snapshot(); panel(); },
      italic() { const o = active(); o.set("fontStyle", o.fontStyle === "italic" ? "normal" : "italic"); o.initDimensions(); canvas.requestRenderAll(); snapshot(); panel(); },
      underline() { const o = active(); o.set("underline", !o.underline); canvas.requestRenderAll(); snapshot(); panel(); },
      uncurve,
      "subir-foto": () => addPhoto(false), "foto-fondo": () => addPhoto(true), "reemplazar-foto": replacePhoto,
      prev: () => nav(-1), next: () => nav(1),
      // rearma la pieza vieja con todo como elementos, conservando lo que se editó recién
      async "hacer-editable"() {
        const b = $(".ed-viejo button");
        b.disabled = true; b.textContent = "Rearmando…";
        await exportar();
        close();
        await onHacerEditable(design);
      },
      fliph() { const o = active(); o.set("flipX", !o.flipX); canvas.requestRenderAll(); snapshot(); },
      flipv() { const o = active(); o.set("flipY", !o.flipY); canvas.requestRenderAll(); snapshot(); },
      "page-center"() { const o = active(); moveRect(o, "hcenter", { left: 0, top: 0, width: design.W, height: design.H }); moveRect(o, "vcenter", { left: 0, top: 0, width: design.W, height: design.H }); canvas.requestRenderAll(); snapshot(); },
      multi() { multi = !multi; toast(multi ? "Tocá los elementos que querés juntar." : "Elegir varios: desactivado."); panel(); },
      copystyle: copyStyle, copy, paste,
      cancel() { close(); },

      // Replicar el logo elegido en las demás piezas del lote: mismo archivo, tamaño, posición y opacidad.
      // Si la otra pieza ya tiene ese logo (o su logo principal), se reemplaza; no queda duplicado.
      // Aplicar el elemento elegido en las demás piezas del lote: mismo tamaño, lugar y estilo.
      // Si ya se había aplicado antes (o es el logo principal), se reemplaza; no queda duplicado.
      async replicar() {
        const o = active();
        if (!o || o.type === "activeSelection") return;
        const others = siblings.filter(d => d !== design);
        const btn = $(".ed-replicar"), hint = $(".ed-rep-hint");
        if (!others.length || !onSaveOther) { hint.textContent = "No hay otras piezas en este lote."; return; }
        if (!o.rid) o.rid = Math.random().toString(36).slice(2, 10);
        const principal = !!o.logo && canvas.getObjects().find(x => x.logo) === o;
        const json = o.toObject(EXTRA), cy = o.getCenterPoint().y;
        btn.disabled = true;
        let ok = 0;
        try {
          for (const [k, d] of others.entries()) {
            hint.textContent = `Aplicando en ${k + 1} de ${others.length}…`;
            const el = document.createElement("canvas");
            const c = new fabric.StaticCanvas(el, { width: d.W, height: d.H, enableRetinaScaling: false });
            await build(c, d);
            let rm = c.getObjects().filter(x => x.rid === o.rid || (o.logo && x.logo === o.logo));
            if (!rm.length && principal) rm = c.getObjects().filter(x => x.logo).slice(0, 1);
            const idx = rm.length ? c.getObjects().indexOf(rm[0]) : -1;
            rm.forEach(x => c.remove(x));
            const [n] = await new Promise(res => fabric.util.enlivenObjects([json], res));
            const k2 = d.W / design.W;
            let top = json.top * k2;
            // otro formato (post / historia): si está en la mitad de abajo, se mantiene la distancia al borde de abajo
            if (d.H !== design.H && cy > design.H / 2) top = d.H - (design.H - json.top) * k2;
            n.set({ left: json.left * k2, top, scaleX: json.scaleX * k2, scaleY: json.scaleY * k2 });
            if (n.bloqueado) applyLock(n, true);
            c.add(n);
            if (idx >= 0) c.moveTo(n, idx);
            c.renderAll();
            d.fabric = c.toJSON(EXTRA);
            delete d.fabric.backgroundImage;
            if (c.fondoFx) d.fabric.fondo_fx = c.fondoFx;
            const blob = await (await fetch(c.toDataURL({ format: "jpeg", quality: 1, multiplier: SALIDA }))).blob();
            c.dispose();
            await onSaveOther(d, blob);
            ok++;
          }
          hint.textContent = `Listo: quedó igual en ${ok} pieza${ok > 1 ? "s" : ""} más. Tocá Guardar para esta.`;
          snapshot();
        } catch (err) {
          hint.textContent = `Se aplicó en ${ok} de ${others.length}. Error: ${err.message || err}`;
        } finally { btn.disabled = false; }
      },
      async save() {
        const blob = await exportar();
        close();
        onSave && onSave(design, blob);
      },
    };
    root.querySelectorAll(".ed-top [data-a], .ed-foot [data-a], .ed-viejo [data-a]").forEach(b => b.onclick = () => actions[b.dataset.a]());
    if (design.rehacible && onHacerEditable) $(".ed-viejo").hidden = false;
    const pos = siblings.indexOf(design);
    if (pos >= 0) $(".ed-pg").textContent = `${pos + 1}/${siblings.length}`;

    async function exportar() {
      canvas.discardActiveObject(); canvas.renderAll();
      // se exporta sin el zoom de pantalla, al tamaño exacto de entrega (W × SALIDA)
      const z = ed.zoom;
      canvas.setDimensions({ width: design.W, height: design.H }); canvas.setZoom(1);
      const url = canvas.toDataURL({ format: "jpeg", quality: 1, multiplier: SALIDA });
      canvas.setDimensions({ width: Math.round(design.W * z), height: Math.round(design.H * z) }); canvas.setZoom(z);
      canvas.calcOffset(); canvas.requestRenderAll();
      design.fabric = canvas.toJSON(EXTRA);
      delete design.fabric.backgroundImage;
      if (canvas.fondoFx) design.fabric.fondo_fx = canvas.fondoFx;
      return (await fetch(url)).blob();
    }
    // guardar e ir a la pieza anterior / siguiente (como pasar de página en Canva)
    async function nav(dir) {
      const i = siblings.indexOf(design) + dir;
      if (i < 0 || i >= siblings.length || !onNav) return;
      const blob = await exportar();
      close();
      if (onSave) await onSave(design, blob);
      onNav(i);
    }

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
      if (!el) { el = document.createElement("div"); el.className = "ed-toast"; el.setAttribute("role", "status"); root.querySelector(".ed-stagew").appendChild(el); }
      el.textContent = t; el.classList.add("on");
      clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove("on"), 2800);
    }

    function onKey(e) {
      const o = active();
      const typing = (o && o.isEditing) || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
      const mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
      if (mod && k === "z" && !typing) { e.preventDefault(); actions[e.shiftKey ? "redo" : "undo"](); return; }
      if (mod && k === "y" && !typing) { e.preventDefault(); actions.redo(); return; }
      if (mod && (k === "+" || k === "=")) { e.preventDefault(); setZoomLevel(ed.zoom * 1.25); return; }
      if (mod && k === "-") { e.preventDefault(); setZoomLevel(ed.zoom / 1.25); return; }
      if (mod && k === "0") { e.preventDefault(); fit(); return; }
      if (mod && k === "c" && !typing && o) { e.preventDefault(); copy(); return; }
      if (mod && k === "v" && !typing) { e.preventDefault(); paste(); return; }
      if (mod && k === "d" && !typing && o) { e.preventDefault(); actions.dup(); return; }
      if (mod && k === "g" && !typing && o) { e.preventDefault(); actions[e.shiftKey ? "ungroup" : "group"](); return; }
      if (mod && k === "a" && !typing) { e.preventDefault(); canvas.discardActiveObject(); const all = canvas.getObjects().filter(x => x.visible !== false && !x.bloqueado); if (all.length) canvas.setActiveObject(all.length > 1 ? new fabric.ActiveSelection(all, { canvas }) : all[0]); canvas.requestRenderAll(); return; }
      // Escape solo suelta la selección (no cierra el editor: se podían perder cambios)
      if (e.key === "Escape" && !typing) { if (o) { canvas.discardActiveObject(); canvas.requestRenderAll(); } return; }
      if (!o || typing) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); actions.del(); }
      const step = e.shiftKey ? 10 : 1;
      const mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (mv && !o.bloqueado) {
        e.preventDefault(); o.set({ left: o.left + mv[0], top: o.top + mv[1] }); o.setCoords(); canvas.requestRenderAll(); snapshot();
        // los números de Posición acompañan el movimiento
        const r = o.getBoundingRect(true, true), nx = $(".ed-panel [data-n=x]"), ny = $(".ed-panel [data-n=y]");
        if (nx) nx.value = Math.round(r.left); if (ny) ny.value = Math.round(r.top);
      }
    }
    document.addEventListener("keydown", onKey);

    // varios cambios juntos (pegar, duplicar o borrar varios) = un solo paso de deshacer
    function batch(fn) { ed.batching = true; try { fn(); } finally { ed.batching = false; } snapshot(); }
    function snapshot() {
      if (!ed || ed.restoring || ed.batching) return;
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
      window.removeEventListener("resize", onResize);
      canvas.dispose(); root.remove(); ed = null;
    }

    panel();
  }

  /** "Redimensionar": pasa lo editado de `src` a la pieza nueva `dst` (otro formato).
   *  rehecha = el servidor ya armó la plantilla en el formato nuevo: se le copian los textos editados
   *  (por nombre) y se suman los elementos que agregó el usuario; si no, se reubica todo. */
  async function convertir(src, dst, rehecha) {
    if (!src.fabric) return null;   // sin edición: la que armó el servidor ya está bien
    const el = document.createElement("canvas");
    const c = new fabric.StaticCanvas(el, { width: dst.W, height: dst.H, enableRetinaScaling: false });
    await build(c, dst);
    const srcObjs = src.fabric.objects || [];
    const tpl = rehecha ? c.getObjects().slice() : [];
    const used = new Set();
    const extra = [];
    for (const so of srcObjs) {
      const match = tpl.find(t => !used.has(t) && t.name && t.name === so.name && t.type === so.type);
      if (match) {
        used.add(match);
        if (so.type === "textbox") match.set({ text: so.text, fill: so.fill, styles: so.styles || {}, charSpacing: so.charSpacing || 0 });
        if (so.logo && so.logo !== match.logo) match.set({ logo: so.logo });
        continue;
      }
      extra.push(so);
    }
    // los de la plantilla que el usuario borró, se borran también: solo los que estaban en la pieza original
    // (por nombre) y ya no están en lo editado. Lo que la versión nueva suma (foto, marco, textura) se queda.
    if (rehecha) {
      const cuenta = list => list.reduce((m, n) => (m[n] = (m[n] || 0) + 1, m), {});
      const antes = cuenta((src.layers || []).map(l => l.name));
      const quedan = cuenta(srcObjs.map(o => o.name));
      const borrar = {};
      Object.keys(antes).forEach(n => { const d = antes[n] - (quedan[n] || 0); if (d > 0 && n !== "Logo") borrar[n] = d; });
      tpl.forEach(t => { if (!used.has(t) && borrar[t.name] > 0) { c.remove(t); borrar[t.name]--; } });
    }
    const k = dst.W / src.W;
    const objs = await new Promise(res => fabric.util.enlivenObjects(extra, res));
    objs.forEach(n => {
      const b = n.getBoundingRect(true, true), cy = b.top + b.height / 2;
      const ty = cy < src.H / 3 ? n.top * k : cy > src.H * 2 / 3 ? dst.H - (src.H - n.top) * k : n.top * dst.H / src.H;
      n.set({ left: n.left * k, top: ty, scaleX: n.scaleX * k, scaleY: n.scaleY * k });
      if (n.bloqueado) applyLock(n, true);
      if (n.foto && n.name === "Foto de fondo") { n.foto.aspecto = dst.W / dst.H; n.set({ left: 0, top: 0 }); n.scale(dst.W / n.width); applyPhoto(n); n.set({ left: 0, top: 0 }); }
      c.add(n);
      if (n.name === "Foto de fondo") n.sendToBack();
    });
    if (src.fabric.background) c.backgroundColor = typeof src.fabric.background === "string" ? src.fabric.background : new fabric.Gradient(src.fabric.background);
    c.renderAll();
    dst.fabric = c.toJSON(EXTRA);
    delete dst.fabric.backgroundImage;
    if (src.fabric.fondo_fx) dst.fabric.fondo_fx = src.fabric.fondo_fx;
    const blob = await (await fetch(c.toDataURL({ format: "jpeg", quality: 1, multiplier: SALIDA }))).blob();
    c.dispose();
    return blob;
  }

  /** Otra plantilla, mismo formato: los textos editados pasan a los de igual nombre (Título, Fecha…),
   *  y lo que se agregó a mano (textos, formas, fotos) se suma tal cual. Lo de la plantilla vieja no. */
  async function cambiarPlantilla(src, dst) {
    if (!src.fabric) return null;
    const el = document.createElement("canvas");
    const c = new fabric.StaticCanvas(el, { width: dst.W, height: dst.H, enableRetinaScaling: false });
    await build(c, dst);
    const deLaPlantilla = new Set((src.layers || []).flatMap(l => [l.name, l.grupo]).filter(Boolean));
    const tpl = c.getObjects().slice(), used = new Set(), extra = [];
    for (const so of src.fabric.objects || []) {
      if (so.type === "textbox") {
        const match = tpl.find(t => !used.has(t) && t.type === "textbox" && t.name && t.name === so.name);
        if (match) { used.add(match); match.set({ text: so.text, styles: so.styles || {} }); continue; }
      }
      if (so.name === "Logo") continue;   // la plantilla nueva trae el suyo
      if (!deLaPlantilla.has(so.name) && so.name !== "Foto de fondo") extra.push(so);
    }
    const k = dst.W / src.W;
    const objs = await new Promise(res => fabric.util.enlivenObjects(extra, res));
    objs.forEach(n => {
      if (k !== 1) n.set({ left: n.left * k, top: n.top * k, scaleX: n.scaleX * k, scaleY: n.scaleY * k });
      if (n.bloqueado) applyLock(n, true);
      c.add(n);
    });
    c.renderAll();
    dst.fabric = c.toJSON(EXTRA);
    delete dst.fabric.backgroundImage;
    const blob = await (await fetch(c.toDataURL({ format: "jpeg", quality: 1, multiplier: SALIDA }))).blob();
    c.dispose();
    return blob;
  }

  const logoUrl = key => "/logos/ver/" + encodeURIComponent(key).replace("%3A", ":");

  window.DEREditor = { render, open, loadFonts, build, convertir, cambiarPlantilla };
})();
