(() => {
  const data = window.__VERA_LAB__;
  if (!data) return;

  const state = {
    runIndex: 0,
    selected: null,
  };

  const body = document.body;
  body.classList.add("show-blocks", "show-chunks", "show-figures");

  function currentRun() {
    return data.runs[state.runIndex];
  }

  function regionStyle(bbox, pageWidth, pageHeight) {
    if (!bbox || bbox.length !== 4 || !pageWidth || !pageHeight) return null;
    const [x0, y0, x1, y1] = bbox;
    return {
      left: `${(x0 / pageWidth) * 100}%`,
      top: `${(y0 / pageHeight) * 100}%`,
      width: `${((x1 - x0) / pageWidth) * 100}%`,
      height: `${((y1 - y0) / pageHeight) * 100}%`,
    };
  }

  function pageDims(pageNumber, run) {
    const page = run.document.pages.find((p) => p.page_number === pageNumber);
    return {
      width: page?.width || null,
      height: page?.height || null,
    };
  }

  function select(kind, id) {
    state.selected = { kind, id };
    document.querySelectorAll(".overlay.selected, .list button.selected").forEach((el) => {
      el.classList.remove("selected");
    });
    document.querySelectorAll(`[data-kind="${kind}"][data-id="${CSS.escape(id)}"]`).forEach((el) => {
      el.classList.add("selected");
    });
    renderDetail();
  }

  function renderDetail() {
    const el = document.getElementById("detail");
    if (!el) return;
    const run = currentRun();
    if (!state.selected) {
      el.textContent = "Select a block, chunk, or figure.";
      return;
    }
    const { kind, id } = state.selected;
    if (kind === "block") {
      const block = run.document.blocks.find((b) => b.block_id === id);
      el.textContent = block
        ? [
            `block_id: ${block.block_id}`,
            `type: ${block.block_type}`,
            `page: ${block.page_number}`,
            `heading_level: ${block.heading_level ?? ""}`,
            `bbox: ${JSON.stringify(block.bbox)}`,
            "",
            block.text || "(empty)",
          ].join("\n")
        : "Block not found.";
      return;
    }
    if (kind === "chunk") {
      const chunk = run.document.chunks.find((c) => c.chunk_id === id);
      el.textContent = chunk
        ? [
            `chunk_id: ${chunk.chunk_id}`,
            `pages: ${chunk.page_start}-${chunk.page_end}`,
            `heading_path: ${chunk.heading_path || "(none)"}`,
            `token_count: ${chunk.token_count}`,
            `block_ids: ${chunk.block_ids.join(", ") || "(none)"}`,
            "",
            chunk.text || "(empty)",
          ].join("\n")
        : "Chunk not found.";
      return;
    }
    if (kind === "figure") {
      const figure = run.document.figures.find((f) => f.block_id === id);
      if (!figure) {
        el.textContent = "Figure not found.";
        return;
      }
      el.innerHTML = "";
      const pre = document.createElement("pre");
      pre.textContent = [
        `block_id: ${figure.block_id}`,
        `page: ${figure.page_number}`,
        `caption: ${figure.caption ?? "(none)"}`,
        `bbox: ${JSON.stringify(figure.bbox)}`,
      ].join("\n");
      el.appendChild(pre);
      if (figure.data_url) {
        const img = document.createElement("img");
        img.src = figure.data_url;
        img.alt = figure.filename || figure.block_id;
        img.style.maxWidth = "100%";
        img.style.marginTop = "0.5rem";
        el.appendChild(img);
      }
    }
  }

  function renderPages() {
    const run = currentRun();
    const root = document.getElementById("pages");
    root.innerHTML = "";
    if (data.pages_omitted) {
      const note = document.createElement("p");
      note.className = "omitted";
      note.textContent = data.pages_omitted_message || "Some pages were omitted from this report.";
      root.appendChild(note);
    }
    for (const pageNumber of data.selected_pages) {
      const rendered = run.rendered_pages[String(pageNumber)] || run.rendered_pages[pageNumber];
      if (!rendered) continue;
      const card = document.createElement("article");
      card.className = "page-card";
      card.id = `page-${pageNumber}`;
      const title = document.createElement("h2");
      title.textContent = `Page ${pageNumber}`;
      card.appendChild(title);
      const surface = document.createElement("div");
      surface.className = "page-surface";
      const img = document.createElement("img");
      img.src = rendered.data_url;
      img.alt = `Page ${pageNumber}`;
      surface.appendChild(img);

      const dims = pageDims(pageNumber, run);
      const pageWidth = dims.width;
      const pageHeight = dims.height;

      for (const block of run.document.blocks.filter((b) => b.page_number === pageNumber)) {
        const style = regionStyle(block.bbox, pageWidth, pageHeight);
        if (!style) continue;
        const box = document.createElement("button");
        box.type = "button";
        const typeClass = ["heading", "paragraph", "table", "caption", "image"].includes(block.block_type)
          ? block.block_type
          : "other";
        box.className = `overlay block ${typeClass}`;
        box.dataset.kind = "block";
        box.dataset.id = block.block_id;
        Object.assign(box.style, style);
        box.title = `${block.block_type} ${block.block_id}`;
        box.addEventListener("click", () => select("block", block.block_id));
        surface.appendChild(box);
      }

      for (const chunk of run.document.chunks) {
        for (const region of chunk.regions || []) {
          if (region.page_number !== pageNumber) continue;
          const style = regionStyle(
            region.bbox,
            region.page_width || pageWidth,
            region.page_height || pageHeight,
          );
          if (!style) continue;
          const box = document.createElement("button");
          box.type = "button";
          box.className = "overlay chunk";
          box.dataset.kind = "chunk";
          box.dataset.id = chunk.chunk_id;
          Object.assign(box.style, style);
          box.title = `chunk ${chunk.chunk_id}`;
          box.addEventListener("click", () => select("chunk", chunk.chunk_id));
          surface.appendChild(box);
        }
      }

      for (const figure of run.document.figures.filter((f) => f.page_number === pageNumber)) {
        const style = regionStyle(
          figure.bbox,
          figure.page_width || pageWidth,
          figure.page_height || pageHeight,
        );
        if (!style) continue;
        const box = document.createElement("button");
        box.type = "button";
        box.className = "overlay figure";
        box.dataset.kind = "figure";
        box.dataset.id = figure.block_id;
        Object.assign(box.style, style);
        box.title = `figure ${figure.block_id}`;
        box.addEventListener("click", () => select("figure", figure.block_id));
        surface.appendChild(box);
      }

      card.appendChild(surface);
      root.appendChild(card);
    }
  }

  function renderLists() {
    const run = currentRun();
    const blocksEl = document.getElementById("block-list");
    const chunksEl = document.getElementById("chunk-list");
    const figuresEl = document.getElementById("figure-list");
    blocksEl.innerHTML = "";
    chunksEl.innerHTML = "";
    figuresEl.innerHTML = "";
    for (const block of run.document.blocks) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kind = "block";
      btn.dataset.id = block.block_id;
      btn.textContent = `p.${block.page_number} · ${block.block_type} · ${block.block_id}`;
      btn.addEventListener("click", () => {
        select("block", block.block_id);
        document.getElementById(`page-${block.page_number}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      blocksEl.appendChild(btn);
    }
    for (const chunk of run.document.chunks) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kind = "chunk";
      btn.dataset.id = chunk.chunk_id;
      const preview = (chunk.text || "").replace(/\s+/g, " ").slice(0, 80);
      btn.textContent = `${chunk.chunk_id} · p.${chunk.page_start}-${chunk.page_end} · ${preview}`;
      btn.addEventListener("click", () => {
        select("chunk", chunk.chunk_id);
        document.getElementById(`page-${chunk.page_start}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      chunksEl.appendChild(btn);
    }
    for (const figure of run.document.figures) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.kind = "figure";
      btn.dataset.id = figure.block_id;
      btn.textContent = `p.${figure.page_number} · ${figure.block_id}${figure.caption ? " · " + figure.caption.slice(0, 40) : ""}`;
      btn.addEventListener("click", () => {
        select("figure", figure.block_id);
        document.getElementById(`page-${figure.page_number}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      figuresEl.appendChild(btn);
    }
  }

  function renderIssues() {
    const run = currentRun();
    const root = document.getElementById("issues");
    root.innerHTML = "";
    if (!run.issues.length) {
      root.innerHTML = '<p class="muted">No issues.</p>';
      return;
    }
    for (const issue of run.issues) {
      const div = document.createElement("div");
      div.className = `issue ${issue.severity}`;
      div.textContent = `[${issue.code}] ${issue.message}`;
      root.appendChild(div);
    }
  }

  function renderStats() {
    const run = currentRun();
    const root = document.getElementById("stats");
    const s = run.stats;
    root.innerHTML = "";
    const dl = document.createElement("dl");
    dl.className = "stats-grid";
    const rows = [
      ["Pages", s.page_count],
      ["Blocks", s.block_count],
      ["Chunks", s.chunk_count],
      ["Figures", s.figure_count],
      ["Tokens min/med/max", `${s.token_count.min} / ${s.token_count.median} / ${s.token_count.max}`],
      ["Single / multi block", `${s.chunk_block_linkage.single_block} / ${s.chunk_block_linkage.multi_block}`],
      ["Blocks by type", Object.entries(s.blocks_by_type).map(([k, v]) => `${k}:${v}`).join(", ") || "—"],
      ["Parser", `${s.parser_name} ${s.parser_version}`.trim()],
      ["Chunking", s.chunking_strategy || "—"],
      ["Mode", s.mode],
    ];
    for (const [k, v] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = String(v);
      dl.appendChild(dt);
      dl.appendChild(dd);
    }
    root.appendChild(dl);
    const hist = document.createElement("div");
    hist.className = "histogram";
    const max = Math.max(0, ...s.token_count.histogram.map((b) => b.count));
    for (const bucket of s.token_count.histogram) {
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.style.height = `${max ? Math.max(4, (bucket.count / max) * 100) : 4}%`;
      bar.title = `${bucket.start}-${bucket.end}: ${bucket.count}`;
      hist.appendChild(bar);
    }
    root.appendChild(hist);
  }

  function renderCompare() {
    const root = document.getElementById("compare");
    if (!root) return;
    if (data.runs.length < 2) {
      root.innerHTML = "";
      return;
    }
    const keys = ["page_count", "block_count", "chunk_count", "figure_count"];
    let html = "<table class='compare-table'><thead><tr><th>Metric</th>";
    for (const run of data.runs) {
      html += `<th>${run.label}</th>`;
    }
    html += "</tr></thead><tbody>";
    for (const key of keys) {
      html += `<tr><td>${key}</td>`;
      for (const run of data.runs) {
        html += `<td>${run.stats[key]}</td>`;
      }
      html += "</tr>";
    }
    html += "<tr><td>issues</td>";
    for (const run of data.runs) {
      html += `<td>${run.issues.length}</td>`;
    }
    html += "</tr></tbody></table>";
    root.innerHTML = html;
  }

  function renderHeader() {
    const run = currentRun();
    document.getElementById("title").textContent = `vera-lab · ${run.label}`;
    document.getElementById("subtitle").textContent =
      `${run.document.source_path} · ${run.document.parser_name} ${run.document.parser_version}`.trim();
    const switcher = document.getElementById("parser-switch");
    if (!switcher) return;
    switcher.innerHTML = "";
    if (data.runs.length < 2) return;
    data.runs.forEach((run, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = run.label;
      if (index === state.runIndex) btn.classList.add("active");
      btn.addEventListener("click", () => {
        state.runIndex = index;
        state.selected = null;
        renderAll();
      });
      switcher.appendChild(btn);
    });
  }

  function renderAll() {
    renderHeader();
    renderPages();
    renderLists();
    renderIssues();
    renderStats();
    renderCompare();
    renderDetail();
  }

  document.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = input.getAttribute("data-layer");
      body.classList.toggle(`show-${layer}`, input.checked);
    });
  });

  renderAll();
})();
