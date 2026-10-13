// Progresivní vylepšení: nahrávání přetažením, originál/náhled, lupa 1:1, živý náhled tónu.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  $$(".print").forEach((el, i) => el.style.setProperty("--i", Math.min(i, 12)));

  // Originál / náhled
  $$("[data-toggle-original]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const img = btn.closest(".print").querySelector("img");
      const showingOriginal = img.src.endsWith(img.dataset.original);
      img.src = showingOriginal ? img.dataset.preview : img.dataset.original;
      btn.textContent = showingOriginal ? "Originál" : "Náhled e-inku";
    });
  });

  // Lupa 1:1
  const loupe = $("[data-loupe]");
  const toggleLoupe = () => loupe && loupe.toggleAttribute("data-zoomed");
  loupe?.addEventListener("click", toggleLoupe);
  $("[data-loupe-toggle]")?.addEventListener("click", toggleLoupe);

  // Nahrávání
  const form = $("[data-upload]");
  const log = $("[data-upload-log]");
  const veil = $("[data-dropveil]");
  const send = async (files) => {
    if (!files.length || !form) return;
    const body = new FormData();
    [...files].forEach((f) => body.append("files", f));
    // Jména souborů jsou nedůvěryhodná: vždy textContent, nikdy innerHTML.
    const show = (lines) => log.replaceChildren(...lines.map(([text, err]) => {
      const li = document.createElement("li");
      li.textContent = text;
      if (err) li.className = "err";
      return li;
    }));
    const n = files.length;
    show([[`Nahrávám ${n} ${n === 1 ? "fotku" : n <= 4 ? "fotky" : "fotek"}…`]]);
    try {
      const res = await fetch("/upload", { method: "POST", body });
      const data = await res.json();
      show([...data.saved.map((name) => [`Přidáno: ${name}`]), ...data.errors.map((e) => [e, true])]);
      if (data.saved.length) setTimeout(() => location.reload(), 700);
    } catch {
      show([["Nahrání se nepovedlo. Zkuste to znovu.", true]]);
    }
  };
  form?.querySelector("input[type=file]").addEventListener("change", (e) => send(e.target.files));
  let depth = 0;
  window.addEventListener("dragenter", (e) => { if (!form || !e.dataTransfer?.types.includes("Files")) return; depth++; veil.hidden = false; });
  window.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; veil.hidden = true; } });
  window.addEventListener("dragover", (e) => { if (form) e.preventDefault(); });
  window.addEventListener("drop", (e) => {
    if (!form) return;
    e.preventDefault(); depth = 0; veil.hidden = true;
    send(e.dataTransfer.files);
  });

  // Živý náhled tónu
  const settings = $("[data-settings]");
  const live = $("[data-live-preview]");
  if (settings) {
    let timer;
    const refresh = () => {
      $$("input[type=range]", settings).forEach((r) => (r.nextElementSibling.value = Number(r.value).toFixed(2)));
      if (!live) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        const q = new URLSearchParams();
        $$("input[type=range], select[name=dither]", settings).forEach((r) => q.set(r.name, r.value));
        const o = $("input[name=orientation]:checked", settings);
        if (o) q.set("orientation", o.value);
        live.toggleAttribute("data-loading", true);
        live.onload = () => live.removeAttribute("data-loading");
        live.src = `${live.dataset.livePreview}?${q}`;
        live.closest(".tone__preview").style.setProperty("--aspect", o?.value === "portrait" ? "3 / 5" : "5 / 3");
      }, 250);
    };
    $$("[data-live]", settings).forEach((el) => el.addEventListener("input", refresh));
    $("[data-tone-reset]", settings)?.addEventListener("click", () => {
      $$("input[data-default]", settings).forEach((r) => (r.value = r.dataset.default));
      refresh();
    });
  }
  // Porovnání originál / e-ink: synchronizovaný zoom a posun, živý tón, podíl barev.
  const cmp = $("[data-compare]");
  if (cmp) {
    const W = Number(cmp.dataset.w), H = Number(cmp.dataset.h);
    const viewports = $$("[data-viewport]", cmp);
    const imgs = { source: $("[data-img=source]", cmp), eink: $("[data-img=eink]", cmp) };
    const allImgs = $$("[data-img]", cmp);  // porovnání: 2 obrázky, varianty: originál + všechny algoritmy
    const sliders = $$("[data-tone] input[type=range], [data-tone] select", cmp);
    const toneSource = $("[data-tone-source]", cmp);
    const usage = $("[data-usage]", cmp);
    const status = $("[data-save-status]", cmp);
    const view = { zoom: "fit", x: 0, y: 0 };

    try { view.zoom = sessionStorage.getItem("inka-zoom") || "fit"; } catch {}
    const zoomInput = $(`input[name=zoom][value="${view.zoom}"]`, cmp);
    if (zoomInput) zoomInput.checked = true; else view.zoom = "fit";

    const clamp = () => {
      if (view.zoom === "fit") return;
      const z = Number(view.zoom), vp = viewports[0];
      view.x = Math.min(0, Math.max(vp.clientWidth - W * z, view.x));
      view.y = Math.min(0, Math.max(vp.clientHeight - H * z, view.y));
    };
    const apply = () => {
      clamp();
      cmp.dataset.zoom = view.zoom;
      allImgs.forEach((img) => {
        if (view.zoom === "fit") {
          img.style.width = "";
          img.style.transform = "";
        } else {
          img.style.width = `${W * Number(view.zoom)}px`;
          img.style.transform = `translate(${view.x}px, ${view.y}px)`;
        }
      });
    };
    $$("input[name=zoom]", cmp).forEach((r) => r.addEventListener("change", () => {
      const vp = viewports[0], old = view.zoom === "fit" ? vp.clientWidth / W : Number(view.zoom);
      const cx = (vp.clientWidth / 2 - view.x) / old, cy = (vp.clientHeight / 2 - view.y) / old;  // držet střed
      view.zoom = r.value;
      try { sessionStorage.setItem("inka-zoom", view.zoom); } catch {}
      if (view.zoom !== "fit") {
        const z = Number(view.zoom);
        view.x = vp.clientWidth / 2 - cx * z;
        view.y = vp.clientHeight / 2 - cy * z;
      }
      apply();
    }));
    viewports.forEach((vp) => {
      let drag = null;
      vp.addEventListener("pointerdown", (e) => {
        if (view.zoom === "fit") return;
        drag = { x: e.clientX - view.x, y: e.clientY - view.y };
        vp.setPointerCapture(e.pointerId);
      });
      vp.addEventListener("pointermove", (e) => {
        if (!drag) return;
        view.x = e.clientX - drag.x;
        view.y = e.clientY - drag.y;
        apply();
      });
      vp.addEventListener("pointerup", () => (drag = null));
      vp.addEventListener("pointercancel", () => (drag = null));
      vp.addEventListener("wheel", (e) => {
        if (view.zoom === "fit") return;
        e.preventDefault();
        view.x -= e.deltaX;
        view.y -= e.deltaY;
        apply();
      }, { passive: false });
    });
    window.addEventListener("resize", apply);

    if (!cmp.dataset.eink) {  // stránka Varianty: jen zoom a posun
      apply();
      return;
    }

    const params = () => {
      const q = new URLSearchParams();
      sliders.forEach((r) => q.set(r.name, r.value));
      return q;
    };
    const same = (a, b) => (isNaN(Number(a)) ? a === b : Number(a) === Number(b));
    const dirty = () => sliders.some((r) => !same(r.value, r.dataset.saved));
    const labels = { black: 0, white: 1, yellow: 2, red: 3, blue: 4, green: 5 };
    const showUsage = (stats) => {
      Object.keys(labels).forEach((name) => {
        const li = $(`[data-color=${name}]`, usage);
        const pct = stats[name] ?? 0;
        li.querySelector(".usage__bar span").style.width = `${Math.min(100, pct)}%`;
        li.querySelector("output").value = `${pct.toFixed(1).replace(".", ",")} %`;
      });
    };
    let timer, seq = 0;
    const refresh = () => {
      sliders.forEach((r) => r.type === "range" && (r.nextElementSibling.value = Number(r.value).toFixed(2)));
      const v = $("[data-variants]", cmp);
      if (v) v.href = `${v.pathname}${dirty() ? `?${params()}` : ""}`;
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const mine = ++seq;
        const q = dirty() ? params() : new URLSearchParams();
        const src = new URLSearchParams(q);
        if (toneSource.checked) src.set("tone", "1");
        cmp.toggleAttribute("data-loading", true);
        // handler před změnou src: obrázek z cache se může načíst dřív než doběhne await níže
        imgs.eink.onload = imgs.eink.onerror = () => mine === seq && cmp.removeAttribute("data-loading");
        imgs.eink.src = `${cmp.dataset.eink}${q.size ? `?${q}` : ""}`;
        imgs.source.src = `${cmp.dataset.src}${src.size ? `?${src}` : ""}`;
        try {
          const stats = await (await fetch(`${cmp.dataset.stats}${q.size ? `?${q}` : ""}`)).json();
          if (mine === seq) showUsage(stats);
        } catch {}
      }, 250);
    };
    sliders.forEach((r) => r.addEventListener(r.type === "range" ? "input" : "change", refresh));
    toneSource.addEventListener("change", refresh);

    $("[data-revert]", cmp).addEventListener("click", () => {
      sliders.forEach((r) => (r.value = r.dataset.saved));
      refresh();
      status.textContent = "Vráceno na uložené hodnoty.";
    });
    $("[data-save]", cmp).addEventListener("click", async () => {
      const body = Object.fromEntries(sliders.map((r) => [r.name, r.type === "range" ? Number(r.value) : r.value]));
      try {
        const res = await fetch("/settings/tone", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(res.status);
        sliders.forEach((r) => (r.dataset.saved = r.value));
        status.textContent = "Uloženo. Rámeček si úpravy vezme při příštím probuzení.";
      } catch {
        status.textContent = "Uložení se nepovedlo.";
      }
    });

    // Šipky: další fotka se stejným zoomem a neuloženými posuvníky.
    const go = (dir) => {
      const q = dirty() ? params() : new URLSearchParams();
      location.href = `${cmp.dataset[dir]}${q.size ? `?${q}` : ""}`;
    };
    $$("[data-nav]", cmp).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); go(a.dataset.nav); }));
    window.addEventListener("keydown", (e) => {
      if (e.target.matches("input, textarea")) return;
      if (e.key === "ArrowLeft") go("prev");
      if (e.key === "ArrowRight") go("next");
    });

    apply();
    refresh();
  }
})();
