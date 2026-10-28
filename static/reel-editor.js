/* Editor de reels de DER Studio.
 *
 * Después de generar un reel se puede: recortar cada clip (inicio y fin), cambiar cuánto dura
 * cada foto, reordenar, sacar clips, elegir la transición de cada corte y su duración, y cambiar
 * título, música y logo. "Aplicar cambios" vuelve a renderizar en el servidor; los clips que no
 * cambiaron se reutilizan, así que es más rápido que la primera vez.
 */
const ReelEditor = (() => {
  const OUTRO = 3, OUTRO_FADE = 0.5, MIN = 0.5, MAX_FOTO = 15;
  const fmt = s => (Math.round(s * 10) / 10).toLocaleString("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const tc = s => { s = Math.max(0, s); const m = Math.floor(s / 60); return `${String(m).padStart(2, "0")}:${fmt(s - m * 60).padStart(4, "0")}`; };
  const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clone = o => JSON.parse(JSON.stringify(o));

  function total(clips) {
    let t = 0;
    clips.forEach((c, i) => {
      const d = c.end - c.start;
      t += d;
      if (i < clips.length - 1 && c.transition !== "none") {
        t -= Math.min(c.transition_seconds, d / 2, (clips[i + 1].end - clips[i + 1].start) / 2);
      }
    });
    return t + OUTRO - OUTRO_FADE;
  }

  /**
   * box: contenedor del resultado. info: { proyecto, transiciones, archivo }.
   * opts.musicas: [[valor, nombre]], opts.logos: html del selector de logo (opcional).
   */
  function open(box, info, opts = {}) {
    const trans = info.transiciones;
    let saved = clone(info.proyecto), p = clone(info.proyecto), archivo = info.archivo, busy = false;

    box.innerHTML = `
      <div class="re-player">
        <video class="final" src="${archivo}" controls playsinline></video>
        <div class="acciones" style="justify-content:center">
          <a class="prim" id="reDl" href="${archivo}" download>Descargar reel (.mp4)</a>
          ${opts.compartir ? `<a href="#" id="reSh">Compartir</a>` : ""}
        </div>
      </div>
      <section class="re" aria-label="Editar reel">
        <div class="re-head">
          <h3>Editar reel</h3>
          <div class="re-total"><small>Duración</small><b id="reTotal">—</b></div>
        </div>
        <p class="re-hint">Tocá la miniatura para ver el tramo. Mové las barras para recortar. Entre clip y clip elegís la transición.</p>
        <ol class="re-tl" id="reTl"></ol>
        <details class="re-more">
          <summary>Título, música y logo</summary>
          <label>Título de apertura</label><input type="text" data-o="title">
          <label>Subtítulo</label><input type="text" data-o="subtitle">
          <div class="row">
            <div><label>Música</label><select data-o="music">${(opts.musicas || []).map(([v, n]) => `<option value="${esc(v)}">${esc(n)}</option>`).join("")}</select></div>
            <div><label>Volumen</label><input type="number" data-o="music_volume" min="0" max="1.5" step="0.1"></div>
          </div>
          <label class="check"><input type="checkbox" id="reNuevaMusica"> Otra canción (misma onda, distinta melodía)</label>
          <label class="check"><input type="checkbox" data-o="keep_original_audio"> Mantener el audio original de los videos</label>
          <label class="check"><input type="checkbox" data-o="watermark"> Logo chico arriba durante el reel</label>
        </details>
        <div class="re-foot">
          <button type="button" class="re-undo" id="reUndo">Deshacer cambios</button>
          <button type="button" class="re-go" id="reGo">Aplicar cambios</button>
        </div>
        <p class="re-status" id="reStatus" role="status"></p>
      </section>`;

    const $ = s => box.querySelector(s);
    const tl = $("#reTl");
    if (opts.compartir) $("#reSh").onclick = ev => { ev.preventDefault(); opts.compartir(archivo); };

    // opciones generales
    box.querySelectorAll("[data-o]").forEach(el => {
      const k = el.dataset.o;
      const pull = () => { const v = p.opciones[k]; el.type === "checkbox" ? (el.checked = !!v) : (el.value = v ?? ""); };
      pull(); el._pull = pull;
      el.oninput = el.onchange = () => {
        p.opciones[k] = el.type === "checkbox" ? el.checked : el.type === "number" ? parseFloat(el.value || 0) : el.value;
        dirty();
      };
    });
    if (![...$("[data-o=music]").options].some(o => o.value === p.opciones.music)) {
      $("[data-o=music]").insertAdjacentHTML("beforeend", `<option value="${esc(p.opciones.music)}">${esc(p.opciones.music)}</option>`);
      $("[data-o=music]").value = p.opciones.music;
    }
    $("#reNuevaMusica").onchange = dirty;

    function dirty() {
      const changed = JSON.stringify(p) !== JSON.stringify(saved) || $("#reNuevaMusica").checked;
      $("#reGo").disabled = busy || !changed;
      $("#reUndo").disabled = busy || !changed;
      $("#reTotal").textContent = tc(total(p.clips));
    }

    function trimRow(c, i) {
      if (c.kind === "foto") {
        return `<div class="re-trim foto">
          <input type="range" min="1" max="${MAX_FOTO}" step="0.5" value="${c.end}" data-k="dur" aria-label="Duración de la foto">
          <div class="re-read"><span>Foto</span><b>${fmt(c.end)} s</b></div></div>`;
      }
      const L = c.source_duration, a = c.start / L * 100, b = c.end / L * 100;
      return `<div class="re-trim">
        <div class="re-track"><div class="re-sel" style="left:${a}%;width:${b - a}%"></div></div>
        <input type="range" min="0" max="${L}" step="0.1" value="${c.start}" data-k="start" aria-label="Inicio del clip ${i + 1}">
        <input type="range" min="0" max="${L}" step="0.1" value="${c.end}" data-k="end" aria-label="Fin del clip ${i + 1}">
        <div class="re-read"><span>${fmt(c.start)} → ${fmt(c.end)} s</span><b>${fmt(c.end - c.start)} s</b></div></div>`;
    }

    function draw() {
      tl.innerHTML = p.clips.map((c, i) => `
        <li class="re-clip" data-i="${i}">
          <button type="button" class="re-thumb" aria-label="Ver el tramo">
            <img src="${c.miniatura}" alt="" loading="eager">
            <span class="re-n">${String(i + 1).padStart(2, "0")}</span>
            ${c.kind === "video" ? `<span class="re-play">▶</span>` : ""}
          </button>
          <div class="re-body">
            <div class="re-name">${esc(c.src.replace(/^\d+_/, ""))}</div>
            ${trimRow(c, i)}
            <div class="re-tools">
              <button type="button" data-a="up" ${i === 0 ? "disabled" : ""} aria-label="Subir">↑</button>
              <button type="button" data-a="down" ${i === p.clips.length - 1 ? "disabled" : ""} aria-label="Bajar">↓</button>
              <button type="button" data-a="del" class="re-del" ${p.clips.length === 1 ? "disabled" : ""}>Quitar</button>
            </div>
          </div>
        </li>
        ${i < p.clips.length - 1 ? `
        <li class="re-tr" data-i="${i}">
          <span class="re-node" aria-hidden="true"></span>
          <select data-t="name" aria-label="Transición entre ${i + 1} y ${i + 2}">
            ${Object.entries(trans).map(([k, n]) => `<option value="${k}" ${k === c.transition ? "selected" : ""}>${esc(n)}</option>`).join("")}
          </select>
          <select data-t="secs" aria-label="Duración de la transición" ${c.transition === "none" ? "disabled" : ""}>
            ${[0.2, 0.3, 0.4, 0.6, 0.8, 1, 1.2].map(v => `<option value="${v}" ${Math.abs(v - c.transition_seconds) < 0.01 ? "selected" : ""}>${fmt(v)} s</option>`).join("")}
          </select>
        </li>` : ""}`).join("");
      bind();
      dirty();
    }

    function bind() {
      tl.querySelectorAll(".re-clip").forEach(li => {
        const i = +li.dataset.i, c = p.clips[i];
        li.querySelectorAll("input[type=range]").forEach(r => r.oninput = () => {
          const v = parseFloat(r.value);
          if (r.dataset.k === "dur") { c.end = Math.min(MAX_FOTO, Math.max(1, v)); c.start = 0; }
          else if (r.dataset.k === "start") { c.start = Math.min(v, c.end - MIN); r.value = c.start; seek(li, c.start); }
          else { c.end = Math.max(v, c.start + MIN); r.value = c.end; seek(li, c.end - 0.05); }
          const sel = li.querySelector(".re-sel");
          if (sel) { sel.style.left = c.start / c.source_duration * 100 + "%"; sel.style.width = (c.end - c.start) / c.source_duration * 100 + "%"; }
          li.querySelector(".re-read").innerHTML = c.kind === "foto"
            ? `<span>Foto</span><b>${fmt(c.end)} s</b>`
            : `<span>${fmt(c.start)} → ${fmt(c.end)} s</span><b>${fmt(c.end - c.start)} s</b>`;
          dirty();
        });
        li.querySelector(".re-thumb").onclick = () => preview(li, c);
        li.querySelectorAll("[data-a]").forEach(b => b.onclick = () => {
          const a = b.dataset.a;
          if (a === "del") p.clips.splice(i, 1);
          else { const j = a === "up" ? i - 1 : i + 1; [p.clips[i], p.clips[j]] = [p.clips[j], p.clips[i]]; }
          draw();
        });
      });
      tl.querySelectorAll(".re-tr").forEach(li => {
        const c = p.clips[+li.dataset.i];
        li.querySelector("[data-t=name]").onchange = e => { c.transition = e.target.value; li.querySelector("[data-t=secs]").disabled = c.transition === "none"; dirty(); };
        li.querySelector("[data-t=secs]").onchange = e => { c.transition_seconds = parseFloat(e.target.value); dirty(); };
      });
    }

    // vista previa del tramo: reemplaza la miniatura por el video liviano y lo reproduce en bucle
    function preview(li, c) {
      if (c.kind !== "video" || !c.vista) return;
      const th = li.querySelector(".re-thumb");
      let v = th.querySelector("video");
      if (v) { v.paused ? v.play() : v.pause(); return; }
      tl.querySelectorAll(".re-thumb video").forEach(o => { o.pause(); o.remove(); });
      v = document.createElement("video");
      v.src = c.vista; v.muted = true; v.playsInline = true; v.preload = "auto";
      v.ontimeupdate = () => { if (v.currentTime >= c.end || v.currentTime < c.start - 0.3) v.currentTime = c.start; };
      v.onloadedmetadata = () => { v.currentTime = c.start; v.play().catch(() => {}); };
      th.appendChild(v); th.classList.add("on");
    }
    function seek(li, t) {
      const v = li.querySelector(".re-thumb video");
      if (v) { v.pause(); v.currentTime = t; }
    }

    $("#reUndo").onclick = () => {
      p = clone(saved); $("#reNuevaMusica").checked = false;
      box.querySelectorAll("[data-o]").forEach(el => el._pull());
      draw();
    };

    $("#reGo").onclick = async () => {
      if (busy) return;
      busy = true; dirty();
      const st = $("#reStatus"), go = $("#reGo");
      if ($("#reNuevaMusica").checked) p.opciones.music_seed = Math.floor(Math.random() * 1e6) + 1;
      go.textContent = "Renderizando…"; st.className = "re-status";
      try {
        const r = await fetch("/api/reel/editar", { method: "POST", headers: { "Content-Type": "application/json" },
                                                    body: JSON.stringify({ lote: p.lote, proyecto: p }) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "No se pudo aplicar.");
        // la app sigue el trabajo en segundo plano: se puede salir y volver (o esperar el aviso)
        if (window.seguirTrabajo) { busy = false; window.seguirTrabajo(j.job, "reel"); return; }
        const t0 = Date.now();
        let s;
        do {
          await new Promise(res => setTimeout(res, 1500));
          s = await (await fetch("/api/reel/" + j.job)).json();
          st.textContent = `Armando la nueva versión… ${Math.round((Date.now() - t0) / 1000)} s`;
        } while (s.estado === "procesando");
        if (s.estado === "error") throw new Error(s.error);
        archivo = s.archivo;
        const vid = box.querySelector("video.final");
        vid.src = archivo; vid.load();
        $("#reDl").href = archivo;
        saved = clone(s.proyecto); p = clone(s.proyecto);
        $("#reNuevaMusica").checked = false;
        st.textContent = `Listo: versión ${p.version}. Ya podés descargarla.`;
        draw();
        vid.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (err) {
        st.className = "re-status err"; st.textContent = String(err.message || err);
      } finally {
        busy = false; go.textContent = "Aplicar cambios"; dirty();
      }
    };

    draw();
  }

  return { open };
})();
