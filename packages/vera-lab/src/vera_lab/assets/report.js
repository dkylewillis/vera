(() => {
  const data = window.__VERA_LAB__;
  if (!data) return;

  const state = {
    runIndex: 0,
    selected: null,
    visiblePage: null,
  };

  const TYPE_COLORS = {
    heading: "var(--heading)",
    paragraph: "var(--paragraph)",
    table: "var(--table)",
    caption: "var(--caption)",
    image: "var(--image)",
  };

  const ARCHIVE_FIELDS = [
    ["title", "Title"],
    ["source_file_name", "Source file"],
    ["source", "Source"],
    ["format_name", "Format"],
    ["format_version", "Format version"],
    ["created_at", "Created"],
    ["archive_size_bytes", "Archive size"],
    ["pages", "Pages"],
    ["chunks", "Chunks"],
    ["attachments", "Attachments"],
    ["default_embedding_model", "Embedding model"],
    ["embedding_model", "Embedding model"],
    ["default_embedding_dimension", "Embedding dimensions"],
    ["default_embedding_normalization", "Normalization"],
    ["parser_name", "Parser"],
    ["parser_version", "Parser version"],
    ["chunking_strategy", "Chunking"],
    ["source_mime_type", "Source type"],
    ["source_file_hash", "Source hash"],
  ];

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
    const page = run.document.pages.find((item) => item.page_number === pageNumber);
    return {
      width: page?.width || null,
      height: page?.height || null,
    };
  }

  function formatValue(key, value) {
    if (value === null || value === undefined || value === "") return "";
    if (key.endsWith("_bytes") && typeof value === "number") return formatBytes(value);
    if (Array.isArray(value)) return value.map((item) => formatValue("", item)).filter(Boolean).join(", ");
    if (typeof value === "object") {
      return Object.entries(value).map(([name, item]) => `${name}: ${formatValue(name, item)}`).join("; ");
    }
    return String(value);
  }

  function formatBytes(size) {
    if (!Number.isFinite(size)) return String(size);
    if (size < 1024) return `${size} B`;
    const units = ["KB", "MB", "GB"];
    let value = size / 1024;
    let unit = units[0];
    for (let index = 0; index < units.length; index += 1) {
      unit = units[index];
      if (value < 1024 || index === units.length - 1) break;
      value /= 1024;
    }
    return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
  }

  function pageSizeLabel(width, height) {
    if (!width || !height) return "";
    const inches = `${(width / 72).toFixed(1)} × ${(height / 72).toFixed(1)} in`;
    return `${Math.round(width)} × ${Math.round(height)} pt · ${inches}`;
  }

  function ocrPages(run) {
    const diagnostics = run.document.diagnostics || {};
    const pages = diagnostics.ocr_pages || diagnostics.ocr_drawn_text_pages || [];
    return new Set((Array.isArray(pages) ? pages : []).map((page) => Number(page)));
  }

  function chunksOnPage(run, pageNumber) {
    return run.document.chunks.filter((chunk) => pageNumber >= chunk.page_start && pageNumber <= chunk.page_end).length;
  }

  function scrollToPage(pageNumber) {
    const pages = document.getElementById("pages");
    const card = document.getElementById(`page-${pageNumber}`);
    if (!pages || !card) return;
    const top = card.getBoundingClientRect().top - pages.getBoundingClientRect().top + pages.scrollTop;
    pages.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
  }

  function select(kind, id) {
    state.selected = { kind, id };
    document.querySelectorAll(".overlay.selected, .overlay.related, .list button.selected").forEach((element) => {
      element.classList.remove("selected", "related");
    });
    const escaped = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(id) : id;
    document.querySelectorAll(`[data-kind="${kind}"][data-id="${escaped}"]`).forEach((element) => {
      element.classList.add("selected");
    });
    const related = chunksForTarget(currentRun(), kind, id);
    for (const chunk of related) {
      const chunkId = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(chunk.chunk_id) : chunk.chunk_id;
      document.querySelectorAll(`.overlay.chunk[data-id="${chunkId}"]`).forEach((element) => {
        element.classList.add("related");
      });
    }
    renderDetail();
    const pin = document.querySelector(".selection-pin");
    if (pin) pin.scrollTop = 0;
  }

  function boxArea(bbox) {
    if (!bbox || bbox.length !== 4) return 0;
    return Math.max(0, bbox[2] - bbox[0]) * Math.max(0, bbox[3] - bbox[1]);
  }

  function centerInside(bbox, regionBbox) {
    if (!bbox || !regionBbox || bbox.length !== 4 || regionBbox.length !== 4) return false;
    const cx = (bbox[0] + bbox[2]) / 2;
    const cy = (bbox[1] + bbox[3]) / 2;
    const [x0, y0, x1, y1] = regionBbox;
    return cx >= Math.min(x0, x1) && cx <= Math.max(x0, x1) && cy >= Math.min(y0, y1) && cy <= Math.max(y0, y1);
  }

  function chunkOwnsBlock(chunk, blockId) {
    if ((chunk.block_ids || []).includes(blockId)) return true;
    return (chunk.regions || []).some((region) => region.block_id === blockId);
  }

  function chunksForTarget(run, kind, id) {
    if (kind === "chunk") {
      const chunk = run.document.chunks.find((item) => item.chunk_id === id);
      return chunk ? [chunk] : [];
    }
    const source = kind === "figure" ? run.document.figures : run.document.blocks;
    const block = source.find((item) => item.block_id === id);
    if (!block) return [];
    const direct = run.document.chunks.filter((chunk) => chunkOwnsBlock(chunk, block.block_id));
    if (direct.length) return direct;
    const geometric = run.document.chunks.filter((chunk) => (chunk.regions || []).some((region) => (
      region.page_number === block.page_number && centerInside(block.bbox, region.bbox)
    )));
    geometric.sort((left, right) => {
      const leftArea = Math.min(...(left.regions || []).map((region) => boxArea(region.bbox)));
      const rightArea = Math.min(...(right.regions || []).map((region) => boxArea(region.bbox)));
      return leftArea - rightArea;
    });
    return geometric.length ? [geometric[0]] : [];
  }

  function blocksForChunk(run, chunk) {
    const ids = new Set(chunk.block_ids || []);
    for (const region of chunk.regions || []) {
      if (region.block_id) ids.add(region.block_id);
    }
    const linked = run.document.blocks.filter((block) => ids.has(block.block_id));
    const extras = run.document.blocks.filter((block) => {
      if (ids.has(block.block_id)) return false;
      const region = (chunk.regions || []).find((item) => (
        item.page_number === block.page_number && centerInside(block.bbox, item.bbox)
      ));
      if (!region) return false;
      return boxArea(block.bbox) <= boxArea(region.bbox) * 1.25;
    });
    return [...linked, ...extras];
  }

  function chunkFacts(chunk) {
    const metadata = chunk.metadata || {};
    const sheet = [metadata.cd_sheet_number, metadata.cd_sheet_title].filter(Boolean).join(" · ");
    return [
      ["Record", metadata.record_type],
      ["Title", metadata.cd_detail_title || metadata.record_label],
      ["Detail", metadata.cd_detail_number || metadata.detail_number],
      ["Detail type", metadata.cd_detail_type_label || metadata.cd_detail_type || metadata.detail_type],
      ["Feature", metadata.cd_feature_type_label || metadata.cd_feature_type],
      ["Description", metadata.cd_description],
      ["Purpose", metadata.cd_purpose_basis],
      ["Sheet", sheet || metadata.sheet_number],
      ["Sheet type", metadata.cd_sheet_type],
      ["Phase", metadata.cd_phase],
      ["Region", metadata.cd_region_type],
      ["Pages", `${chunk.page_start}–${chunk.page_end}`],
      ["Heading", chunk.heading_path],
    ];
  }

  const SHOWN_METADATA = new Set([
    "record_type", "record_label", "cd_sheet_number", "sheet_number", "cd_sheet_title",
    "cd_sheet_type", "cd_phase", "cd_region_type", "cd_detail_number", "detail_number",
    "cd_detail_type", "detail_type", "cd_detail_type_label", "cd_detail_title",
    "cd_description", "cd_feature_type", "cd_feature_type_label", "cd_purpose_basis",
    "cd_record", "document_id", "source_filename",
  ]);

  function appendBlockBody(element, run, block) {
    const figure = run.document.figures.find((item) => item.block_id === block.block_id);
    const title = document.createElement("p");
    title.className = "block-ref";
    title.textContent = `${block.block_type || "block"} · ${block.block_id} · page ${block.page_number}`;
    element.appendChild(title);
    if (block.text) {
      const bodyText = document.createElement("pre");
      bodyText.className = "body";
      bodyText.textContent = block.text;
      element.appendChild(bodyText);
    }
    if (figure && figure.data_url) {
      const image = document.createElement("img");
      image.src = figure.data_url;
      image.alt = figure.filename || figure.block_id;
      image.style.maxWidth = "100%";
      image.style.marginTop = "0.35rem";
      element.appendChild(image);
    }
  }

  function appendChunkRecord(element, run, chunk) {
    const metadata = chunk.metadata || {};
    const heading = document.createElement("h4");
    heading.className = "selection-title";
    heading.textContent = metadata.cd_detail_title || metadata.record_label || metadata.cd_sheet_title || chunk.chunk_id;
    element.appendChild(heading);
    appendFacts(element, chunkFacts(chunk));
    const extra = Object.entries(metadata).filter(([key, value]) => !SHOWN_METADATA.has(key) && formatValue(key, value));
    if (extra.length) appendFacts(element, extra.map(([key, value]) => [key.replace(/^cd_/, "").replaceAll("_", " "), value]));
    const blocks = blocksForChunk(run, chunk);
    if (blocks.length) {
      const label = document.createElement("h4");
      label.className = "selection-sub";
      label.textContent = "Blocks in this record";
      element.appendChild(label);
      for (const block of blocks) appendBlockBody(element, run, block);
      return;
    }
    const bodyText = document.createElement("pre");
    bodyText.className = "body";
    bodyText.textContent = chunk.text || "(empty)";
    element.appendChild(bodyText);
  }

  function appendNoteList(parent, label, values, className) {
    const items = Array.isArray(values) ? values : (values ? [values] : []);
    const lines = items.map((item) => formatValue("", item)).filter(Boolean);
    if (!lines.length) return;
    const block = document.createElement("div");
    block.className = className;
    const title = document.createElement("h4");
    title.textContent = label;
    block.appendChild(title);
    for (const line of lines) {
      const row = document.createElement("p");
      row.textContent = line;
      block.appendChild(row);
    }
    parent.appendChild(block);
  }

  function appendFacts(parent, rows) {
    const list = document.createElement("dl");
    list.className = parent.classList.contains("detail") ? "kv" : "facts";
    for (const [label, value] of rows) {
      const shown = formatValue("", value);
      if (!shown) continue;
      const term = document.createElement("dt");
      term.textContent = label;
      const definition = document.createElement("dd");
      definition.textContent = shown;
      list.appendChild(term);
      list.appendChild(definition);
    }
    if (!list.childElementCount) return;
    parent.appendChild(list);
  }

  function renderDetail() {
    const element = document.getElementById("detail");
    if (!element) return;
    const run = currentRun();
    element.replaceChildren();
    if (!state.selected) {
      element.textContent = "Select a block, chunk, or figure on the page.";
      return;
    }
    const { kind, id } = state.selected;
    const records = chunksForTarget(run, kind, id);
    if (kind === "chunk" && !records.length) {
      element.textContent = "Chunk not found.";
      return;
    }
    for (const chunk of records) appendChunkRecord(element, run, chunk);
    if (kind === "block") {
      const block = run.document.blocks.find((item) => item.block_id === id);
      if (!block) {
        if (!records.length) element.textContent = "Block not found.";
        return;
      }
      const alreadyShown = records.some((chunk) => blocksForChunk(run, chunk).some((item) => item.block_id === id));
      if (!alreadyShown) appendBlockBody(element, run, block);
      return;
    }
    if (kind === "figure") {
      const figure = run.document.figures.find((item) => item.block_id === id);
      if (!figure) {
        if (!records.length) element.textContent = "Figure not found.";
        return;
      }
      const alreadyShown = records.some((chunk) => blocksForChunk(run, chunk).some((item) => item.block_id === id));
      if (!alreadyShown) {
        appendFacts(element, [
          ["Figure", figure.block_id],
          ["Page", figure.page_number],
          ["Caption", figure.caption],
          ["File", figure.filename],
          ["Type", figure.mime_type],
        ]);
        if (figure.data_url) {
          const image = document.createElement("img");
          image.src = figure.data_url;
          image.alt = figure.filename || figure.block_id;
          image.style.maxWidth = "100%";
          image.style.marginTop = "0.5rem";
          element.appendChild(image);
        }
      }
    }
  }

  function renderPages() {
    const run = currentRun();
    const root = document.getElementById("pages");
    root.replaceChildren();
    const ocr = ocrPages(run);
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
      const dims = pageDims(pageNumber, run);
      const size = pageSizeLabel(dims.width, dims.height);
      if (size || ocr.has(Number(pageNumber))) {
        const meta = document.createElement("span");
        meta.className = "page-meta";
        meta.textContent = [size, ocr.has(Number(pageNumber)) ? "OCR" : ""].filter(Boolean).join(" · ");
        title.appendChild(meta);
      }
      card.appendChild(title);
      const surface = document.createElement("div");
      surface.className = "page-surface";
      const image = document.createElement("img");
      image.src = rendered.data_url;
      image.alt = `Page ${pageNumber}`;
      surface.appendChild(image);
      const pageWidth = dims.width;
      const pageHeight = dims.height;

      for (const block of run.document.blocks.filter((item) => item.page_number === pageNumber)) {
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
          const recordType = chunk.metadata?.record_type;
          box.title = [recordType, chunk.chunk_id, chunk.heading_path].filter(Boolean).join(" · ");
          box.addEventListener("click", () => select("chunk", chunk.chunk_id));
          surface.appendChild(box);
        }
      }

      for (const figure of run.document.figures.filter((item) => item.page_number === pageNumber)) {
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
    watchPages();
  }

  function watchPages() {
    const root = document.getElementById("pages");
    if (!root || typeof IntersectionObserver === "undefined") return;
    if (state.pageObserver) state.pageObserver.disconnect();
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
      if (!visible) return;
      const pageNumber = Number(visible.target.id.replace("page-", ""));
      if (!pageNumber || pageNumber === state.visiblePage) return;
      state.visiblePage = pageNumber;
      document.querySelectorAll(".page-rail button").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.page) === pageNumber);
      });
    }, { root, threshold: [0, 0.15, 0.5] });
    root.querySelectorAll(".page-card").forEach((card) => observer.observe(card));
    state.pageObserver = observer;
  }

  function renderPageRail() {
    const run = currentRun();
    const root = document.getElementById("page-rail");
    if (!root) return;
    root.replaceChildren();
    const ocr = ocrPages(run);
    const counts = data.selected_pages.map((pageNumber) => chunksOnPage(run, pageNumber));
    const max = Math.max(1, ...counts);
    data.selected_pages.forEach((pageNumber, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.page = String(pageNumber);
      const label = document.createElement("span");
      label.textContent = String(pageNumber);
      button.appendChild(label);
      if (ocr.has(Number(pageNumber))) {
        const mark = document.createElement("span");
        mark.className = "ocr-mark";
        mark.textContent = "OCR";
        button.appendChild(mark);
      }
      const meter = document.createElement("span");
      meter.className = "meter";
      const fill = document.createElement("span");
      fill.style.width = `${(counts[index] / max) * 100}%`;
      meter.appendChild(fill);
      button.appendChild(meter);
      button.title = `${counts[index]} chunk${counts[index] === 1 ? "" : "s"} on page ${pageNumber}`;
      if (index === 0) button.classList.add("active");
      button.addEventListener("click", () => scrollToPage(pageNumber));
      root.appendChild(button);
    });
  }

  function renderLists() {
    const run = currentRun();
    const blocksEl = document.getElementById("block-list");
    const chunksEl = document.getElementById("chunk-list");
    const figuresEl = document.getElementById("figure-list");
    blocksEl.replaceChildren();
    chunksEl.replaceChildren();
    figuresEl.replaceChildren();
    for (const block of run.document.blocks) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.kind = "block";
      button.dataset.id = block.block_id;
      const preview = (block.text || "").replace(/\s+/g, " ").slice(0, 72);
      button.textContent = `p.${block.page_number} · ${block.block_type} · ${preview || block.block_id}`;
      button.addEventListener("click", () => {
        select("block", block.block_id);
        scrollToPage(block.page_number);
      });
      blocksEl.appendChild(button);
    }
    for (const chunk of run.document.chunks) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.kind = "chunk";
      button.dataset.id = chunk.chunk_id;
      const metadata = chunk.metadata || {};
      const kind = metadata.record_type || metadata.record_label;
      const sheet = metadata.cd_sheet_number || metadata.sheet_number;
      const preview = (chunk.heading_path || chunk.text || "").replace(/\s+/g, " ").slice(0, 72);
      button.textContent = [
        `p.${chunk.page_start}${chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}`,
        kind,
        sheet,
        preview,
      ].filter(Boolean).join(" · ");
      button.addEventListener("click", () => {
        select("chunk", chunk.chunk_id);
        scrollToPage(chunk.page_start);
      });
      chunksEl.appendChild(button);
    }
    for (const figure of run.document.figures) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.kind = "figure";
      button.dataset.id = figure.block_id;
      button.textContent = `p.${figure.page_number} · ${figure.caption ? figure.caption.slice(0, 48) : figure.block_id}`;
      button.addEventListener("click", () => {
        select("figure", figure.block_id);
        scrollToPage(figure.page_number);
      });
      figuresEl.appendChild(button);
    }
  }

  function renderIssues() {
    const run = currentRun();
    const root = document.getElementById("issues");
    root.replaceChildren();
    if (!run.issues.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No layout issues.";
      root.appendChild(empty);
      return;
    }
    for (const issue of run.issues) {
      const row = document.createElement("div");
      row.className = `issue ${issue.severity}`;
      row.textContent = `[${issue.code}] ${issue.message}`;
      root.appendChild(row);
    }
  }

  function renderStats() {
    const run = currentRun();
    const root = document.getElementById("stats");
    const stats = run.stats;
    root.replaceChildren();
    const rows = [
      ["Pages", stats.page_count],
      ["Blocks", stats.block_count],
      ["Chunks", stats.chunk_count],
      ["Figures", stats.figure_count],
      ["Tokens", `${stats.token_count.min} / ${Math.round(stats.token_count.median)} / ${stats.token_count.max}`],
      ["Total tokens", stats.token_count.total],
      ["One block", stats.chunk_block_linkage.single_block],
      ["Several blocks", stats.chunk_block_linkage.multi_block],
      ["No blocks", stats.chunk_block_linkage.zero_block],
    ];
    const list = document.createElement("dl");
    list.className = "facts";
    for (const [label, value] of rows) {
      const term = document.createElement("dt");
      term.textContent = label;
      const definition = document.createElement("dd");
      definition.textContent = String(value);
      list.appendChild(term);
      list.appendChild(definition);
    }
    root.appendChild(list);
    const entries = Object.entries(stats.blocks_by_type || {});
    const total = entries.reduce((sum, [, count]) => sum + count, 0);
    if (total) {
      const bar = document.createElement("div");
      bar.className = "type-bar";
      bar.title = entries.map(([name, count]) => `${name} ${count}`).join(", ");
      for (const [name, count] of entries) {
        const segment = document.createElement("span");
        segment.style.width = `${(count / total) * 100}%`;
        segment.style.background = TYPE_COLORS[name] || "var(--muted)";
        bar.appendChild(segment);
      }
      root.appendChild(bar);
      const legend = document.createElement("div");
      legend.className = "legend";
      for (const [name, count] of entries) {
        const item = document.createElement("span");
        const swatch = document.createElement("i");
        swatch.style.background = TYPE_COLORS[name] || "var(--muted)";
        item.append(swatch, `${name} ${count}`);
        legend.appendChild(item);
      }
      root.appendChild(legend);
    }
    const histogram = document.createElement("div");
    histogram.className = "histogram";
    const peak = Math.max(0, ...stats.token_count.histogram.map((bucket) => bucket.count));
    for (const bucket of stats.token_count.histogram) {
      const column = document.createElement("div");
      column.className = "bar";
      column.style.height = `${peak ? Math.max(4, (bucket.count / peak) * 100) : 4}%`;
      column.title = `${bucket.start}–${bucket.end} tokens: ${bucket.count}`;
      histogram.appendChild(column);
    }
    root.appendChild(histogram);
  }

  function renderArchive() {
    const run = currentRun();
    const root = document.getElementById("archive");
    if (!root) return;
    root.replaceChildren();
    const heading = document.createElement("h3");
    heading.textContent = "Archive";
    root.appendChild(heading);
    const archive = run.document.archive || {};
    const seen = new Set();
    const rows = [];
    for (const [key, label] of ARCHIVE_FIELDS) {
      if (archive[key] === undefined || archive[key] === null || archive[key] === "" || seen.has(label)) continue;
      if (key === "embedding_model" && archive.default_embedding_model) continue;
      seen.add(label);
      rows.push([label, archive[key]]);
    }
    if (!rows.length) {
      rows.push(
        ["Parser", `${run.document.parser_name} ${run.document.parser_version}`.trim()],
        ["Chunking", run.document.chunking_strategy],
        ["Mode", run.document.mode],
        ["Pages", run.document.page_count],
        ["Blocks", run.document.block_count],
        ["Chunks", run.document.chunk_count],
        ["Figures", run.document.figure_count],
      );
    }
    appendFacts(root, rows);
    const diagnostics = run.document.diagnostics || {};
    const ocrRows = [
      ["OCR engine", diagnostics.ocr_engine || diagnostics.engine],
      ["OCR mode", diagnostics.ocr_mode],
      ["OCR language", diagnostics.ocr_language],
      ["OCR DPI", diagnostics.ocr_dpi],
      ["OCR pages", diagnostics.ocr_pages],
      ["Drawn-text pages", diagnostics.ocr_drawn_text_pages],
      ["Recovered pages", diagnostics.recovered_pages],
    ].filter(([, value]) => value !== undefined && value !== null && value !== "" && !(Array.isArray(value) && !value.length));
    if (ocrRows.length) appendFacts(root, ocrRows);
    const counts = new Map();
    for (const chunk of run.document.chunks) {
      const recordType = chunk.metadata?.record_type;
      if (!recordType) continue;
      counts.set(recordType, (counts.get(recordType) || 0) + 1);
    }
    if (counts.size) {
      const chips = document.createElement("div");
      chips.className = "chips";
      for (const [recordType, count] of [...counts.entries()].sort((left, right) => right[1] - left[1])) {
        const chip = document.createElement("span");
        chip.className = "chip";
        const name = document.createElement("strong");
        name.textContent = recordType;
        chip.append(name, ` ${count}`);
        chips.appendChild(chip);
      }
      root.appendChild(chips);
    }
    appendNoteList(root, "Warnings", archive.ingest_warnings, "archive-notes");
    appendNoteList(root, "Notes", archive.ingest_notes, "archive-notes notes");
    const shown = new Set(ARCHIVE_FIELDS.map(([key]) => key));
    shown.add("metadata");
    shown.add("ocr");
    shown.add("path");
    shown.add("page_count");
    shown.add("ingest_warnings");
    shown.add("ingest_notes");
    shown.add("viewer_pages_attachment_id");
    shown.add("viewer_blocks_attachment_id");
    shown.add("viewer_preview_attachment_id");
    shown.add("source_attachment_id");
    const extra = Object.entries(archive).filter(([key, value]) => {
      if (shown.has(key) || key.endsWith("_attachment_id")) return false;
      return Boolean(formatValue(key, value));
    });
    if (extra.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${extra.length} more field${extra.length === 1 ? "" : "s"}`;
      details.appendChild(summary);
      appendFacts(details, extra.map(([key, value]) => [key, value]));
      root.appendChild(details);
    }
  }

  function renderCompare() {
    const root = document.getElementById("compare");
    const section = root?.closest("section");
    if (!root) return;
    if (data.runs.length < 2) {
      root.replaceChildren();
      if (section) section.hidden = true;
      return;
    }
    if (section) section.hidden = false;
    const keys = ["page_count", "block_count", "chunk_count", "figure_count"];
    let html = "<table class='compare-table'><thead><tr><th>Metric</th>";
    for (const run of data.runs) html += `<th>${run.label}</th>`;
    html += "</tr></thead><tbody>";
    for (const key of keys) {
      html += `<tr><td>${key}</td>`;
      for (const run of data.runs) html += `<td>${run.stats[key]}</td>`;
      html += "</tr>";
    }
    html += "<tr><td>issues</td>";
    for (const run of data.runs) html += `<td>${run.issues.length}</td>`;
    html += "</tr></tbody></table>";
    root.innerHTML = html;
  }

  function renderHeader() {
    const run = currentRun();
    const archive = run.document.archive || {};
    const name = archive.source_file_name || archive.title || run.label;
    document.getElementById("title").textContent = name;
    const model = archive.default_embedding_model || archive.embedding_model || "";
    document.getElementById("subtitle").textContent = [
      run.document.source_path,
      [run.document.parser_name, run.document.parser_version].filter(Boolean).join(" "),
      model,
    ].filter(Boolean).join(" · ");
    const switcher = document.getElementById("parser-switch");
    if (!switcher) return;
    switcher.replaceChildren();
    if (data.runs.length < 2) return;
    data.runs.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      if (index === state.runIndex) button.classList.add("active");
      button.addEventListener("click", () => {
        state.runIndex = index;
        state.selected = null;
        state.visiblePage = null;
        renderAll();
      });
      switcher.appendChild(button);
    });
  }

  function renderAll() {
    renderHeader();
    renderArchive();
    renderPageRail();
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
