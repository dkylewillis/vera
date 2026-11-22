(() => {
  const data = window.__VERA_LAB__;
  if (!data) return;

  const state = {
    runIndex: 0,
    selected: null,
    visiblePage: null,
  };

  const body = document.body;
  const BLOCK_TYPES = ["paragraph", "heading", "table", "caption", "image", "other"];
  body.classList.add(...BLOCK_TYPES.map((type) => `show-${type}`));

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
    const linked = new Set();
    for (const chunk of related) {
      for (const blockId of chunk.block_ids || []) linked.add(blockId);
      for (const region of chunk.regions || []) {
        if (region.block_id) linked.add(region.block_id);
      }
    }
    if (kind === "block") linked.delete(id);
    for (const blockId of linked) {
      const blockKey = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(blockId) : blockId;
      document.querySelectorAll(`.overlay.block[data-id="${blockKey}"]`).forEach((element) => {
        element.classList.add(kind === "block" ? "related" : "selected");
      });
    }
    renderDetail();
    showTab("chunk");
    const body = document.querySelector(".inspector-body");
    if (body) body.scrollTop = 0;
  }

  function showTab(name) {
    document.querySelectorAll(".inspector-tabs button").forEach((button) => {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.hidden = panel.dataset.panel !== name;
    });
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

  const DEFAULT_REGION_KEYS = new Set([
    "block_id", "kind", "page_number", "bbox", "page_width", "page_height",
  ]);

  function keyClass(origin) {
    return origin === "pipeline" ? "key-pipeline" : "key-default";
  }

  function isPlainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function isLongList(value) {
    return Array.isArray(value)
      && value.length > 0
      && value.every((item) => typeof item === "string")
      && (value.length > 4 || value.some((item) => item.length > 80));
  }

  function isStructured(value) {
    return isPlainObject(value)
      || isLongList(value)
      || (Array.isArray(value) && value.some((item) => isPlainObject(item)));
  }

  function keyText(term, key) {
    const parts = String(key).split("_");
    parts.forEach((part, index) => {
      if (index) term.append("_");
      term.append(document.createTextNode(part));
      if (index < parts.length - 1) term.append(document.createElement("wbr"));
    });
  }

  function appendStructured(parent, key, value, origin) {
    if (isPlainObject(value)) {
      const entries = Object.entries(value).sort((left, right) => left[0].localeCompare(right[0]));
      appendStore(parent, key, {
        nested: true,
        rows: entries,
        origin,
        nameClass: keyClass(origin),
      });
      return;
    }
    const block = document.createElement("div");
    block.className = "field-block";
    const head = document.createElement("div");
    head.className = "field-head";
    const term = document.createElement("span");
    term.className = keyClass(origin);
    keyText(term, key);
    const count = document.createElement("span");
    count.className = "value-count";
    count.textContent = String(value.length);
    head.append(term, count);
    block.appendChild(head);
    if (isLongList(value)) {
      const items = document.createElement("ul");
      items.className = "value-list";
      for (const item of value) {
        const row = document.createElement("li");
        row.textContent = item;
        items.appendChild(row);
      }
      block.appendChild(items);
    } else {
      const columns = [];
      for (const item of value) {
        if (!isPlainObject(item)) continue;
        for (const name of Object.keys(item)) {
          if (!columns.includes(name)) columns.push(name);
        }
      }
      columns.sort((left, right) => left.localeCompare(right));
      const scroll = document.createElement("div");
      scroll.className = "value-scroll";
      const table = document.createElement("table");
      const headRow = document.createElement("tr");
      for (const name of columns) {
        const cell = document.createElement("th");
        cell.className = keyClass(origin);
        keyText(cell, name);
        headRow.appendChild(cell);
      }
      const thead = document.createElement("thead");
      thead.appendChild(headRow);
      const tbody = document.createElement("tbody");
      for (const item of value) {
        const row = document.createElement("tr");
        for (const name of columns) {
          const cell = document.createElement("td");
          const itemValue = isPlainObject(item) ? item[name] : "";
          cell.textContent = itemValue == null ? "" : formatValue(name, itemValue);
          row.appendChild(cell);
        }
        tbody.appendChild(row);
      }
      table.append(thead, tbody);
      scroll.appendChild(table);
      block.appendChild(scroll);
    }
    parent.appendChild(block);
  }

  function appendKeys(parent, rows, originFor = () => "default") {
    if (!rows.length) return;
    const scalars = rows.filter(([, value]) => !isStructured(value));
    const structured = rows.filter(([, value]) => isStructured(value));
    if (scalars.length) {
      const list = document.createElement("dl");
      list.className = "facts";
      for (const [key, value] of scalars) {
        const term = document.createElement("dt");
        term.className = keyClass(originFor(key));
        keyText(term, key);
        const definition = document.createElement("dd");
        definition.textContent = formatValue(key, value);
        list.append(term, definition);
      }
      parent.appendChild(list);
    }
    for (const [key, value] of structured) appendStructured(parent, key, value, originFor(key));
  }

  function appendStore(parent, name, { rows = [], names = [], nested = false, origin = "default", nameClass = "" } = {}) {
    const originFor = typeof origin === "function" ? origin : () => origin;
    const block = document.createElement("section");
    block.className = nested ? "store nested" : "store";
    const title = document.createElement(nested ? "h4" : "h3");
    title.className = nameClass ? `store-name ${nameClass}` : "store-name";
    keyText(title, name);
    block.appendChild(title);
    if (names.length) {
      const list = document.createElement("ul");
      list.className = "columns";
      for (const column of names) {
        const item = document.createElement("li");
        item.textContent = column;
        item.className = keyClass(originFor(column));
        list.appendChild(item);
      }
      block.appendChild(list);
    }
    if (rows.length) appendKeys(block, rows, originFor);
    parent.appendChild(block);
    return block;
  }

  function storedKeys(chunk) {
    const metadata = {
      page_start: chunk.page_start,
      page_end: chunk.page_end,
      heading_path: chunk.heading_path,
      token_count: chunk.token_count,
      ...(chunk.metadata || {}),
    };
    return Object.entries(metadata)
      .filter(([, value]) => value !== undefined && value !== null)
      .sort((left, right) => left[0].localeCompare(right[0]));
  }

  function storedBlockRows(block) {
    return [
      ["block_id", block.block_id],
      ["page_number", block.page_number],
      ["block_type", block.block_type],
      ["bbox", block.bbox],
      ["heading_level", block.heading_level],
      ["sort_order", block.sort_order],
    ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  }

  function appendViewerBlock(element, run, block) {
    const linked = appendStore(element, "viewer_blocks", {
      nested: true,
      rows: storedBlockRows(block),
      origin: "default",
    });
    if (block.text) {
      const label = document.createElement("div");
      label.className = "field-head";
      const term = document.createElement("span");
      term.className = "key-default";
      term.textContent = "text";
      label.appendChild(term);
      const text = document.createElement("pre");
      text.className = "body";
      text.textContent = block.text;
      linked.append(label, text);
    }
    const figure = run.document.figures.find((item) => item.block_id === block.block_id);
    if (figure && figure.data_url) {
      const image = document.createElement("img");
      image.src = figure.data_url;
      image.alt = figure.filename || figure.block_id;
      image.style.maxWidth = "100%";
      image.style.marginTop = "0.35rem";
      linked.appendChild(image);
    }
    return linked;
  }

  function appendRegionLink(parent, region) {
    const group = document.createElement("div");
    group.className = "region-link";
    appendKeys(group, [
      ["block_id", region.block_id],
      ["page_number", region.page_number],
      ["bbox", region.bbox],
      ["page_width", region.page_width],
      ["page_height", region.page_height],
    ].filter(([, value]) => value !== undefined && value !== null && value !== ""), () => "default");
    parent.appendChild(group);
  }

  function appendChunkRecord(element, run, chunk) {
    const schema = run.document.schema || {};
    const base = new Set(schema.base_chunk_keys || []);
    const record = appendStore(element, "chunks", {
      rows: [["chunk_id", chunk.chunk_id]],
      origin: "default",
    });
    const metadata = appendStore(record, "metadata_json", {
      nested: true,
      rows: storedKeys(chunk),
      origin: (key) => (base.has(key) ? "default" : "pipeline"),
    });
    const regions = chunk.regions || [];
    if (regions.length) {
      const regionStore = appendStore(metadata, "regions", {
        nested: true,
        origin: "default",
        nameClass: "key-default",
      });
      const count = document.createElement("span");
      count.className = "value-count";
      count.textContent = String(regions.length);
      regionStore.querySelector(".store-name")?.append(count);
      for (const region of regions) appendRegionLink(regionStore, region);
      const seen = new Set();
      for (const region of regions) {
        if (!region.block_id || seen.has(region.block_id)) continue;
        seen.add(region.block_id);
        const block = run.document.blocks.find((item) => item.block_id === region.block_id);
        if (block) appendViewerBlock(record, run, block);
      }
      return;
    }
    const bodyText = document.createElement("pre");
    bodyText.className = "body";
    bodyText.textContent = chunk.text || "(empty)";
    element.appendChild(bodyText);
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
      element.textContent = "Click a region on the sheet. Its metadata_json opens here.";
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
      const alreadyShown = records.some((chunk) => (chunk.regions || []).some((region) => region.block_id === id));
      if (!alreadyShown) appendViewerBlock(element, run, block);
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
      const sheet = sheetOnPage(run, pageNumber);
      const sheetMeta = sheet?.metadata || {};
      const sheetName = sheetMeta.cd_sheet_number || sheetMeta.record_label || "";
      const sheetTitle = sheetMeta.cd_sheet_title || "";
      title.textContent = [`Page ${pageNumber}`, sheetName, sheetTitle].filter(Boolean).join(" · ");
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
        const owner = run.document.chunks.find((chunk) => (
          (chunk.block_ids || []).includes(block.block_id)
          || (chunk.regions || []).some((region) => region.block_id === block.block_id)
        ));
        const metadata = owner?.metadata || {};
        box.title = [
          block.block_type,
          block.block_id,
          metadata.record_type,
          metadata.record_label || metadata.cd_detail_title,
        ].filter(Boolean).join(" · ");
        box.addEventListener("click", () => select("block", block.block_id));
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
      syncPager();
    }, { root, threshold: [0, 0.15, 0.5] });
    root.querySelectorAll(".page-card").forEach((card) => observer.observe(card));
    state.pageObserver = observer;
  }

  function sheetOnPage(run, pageNumber) {
    return run.document.chunks.find((chunk) => {
      const metadata = chunk.metadata || {};
      return metadata.record_type === "sheet"
        && pageNumber >= chunk.page_start
        && pageNumber <= chunk.page_end;
    });
  }

  function pageCaption(run, pageNumber) {
    const sheet = sheetOnPage(run, pageNumber);
    const metadata = sheet?.metadata || {};
    return [metadata.cd_sheet_number || metadata.record_label, metadata.cd_sheet_title]
      .filter(Boolean)
      .join(" · ");
  }

  function syncPager() {
    const pages = data.selected_pages || [];
    const pageNumber = state.visiblePage || pages[0];
    const index = pages.indexOf(pageNumber);
    const field = document.querySelector(".pager-input");
    if (field && document.activeElement !== field) field.value = pageNumber ? String(pageNumber) : "";
    const sheet = document.getElementById("pager-sheet");
    if (sheet) sheet.textContent = pageNumber ? pageCaption(currentRun(), pageNumber) : "";
    const prev = document.querySelector(".pager-step[data-dir='-1']");
    const next = document.querySelector(".pager-step[data-dir='1']");
    if (prev) prev.disabled = index <= 0;
    if (next) next.disabled = index < 0 || index >= pages.length - 1;
  }

  function renderPager() {
    const root = document.getElementById("pager");
    if (!root) return;
    root.replaceChildren();
    const pages = data.selected_pages || [];
    if (!pages.length) return;
    if (!state.visiblePage) state.visiblePage = pages[0];
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "pager-step";
    prev.dataset.dir = "-1";
    prev.setAttribute("aria-label", "Previous page");
    prev.textContent = "‹";
    const field = document.createElement("input");
    field.type = "number";
    field.className = "pager-input";
    field.min = String(pages[0]);
    field.max = String(pages[pages.length - 1]);
    field.value = String(state.visiblePage);
    field.setAttribute("aria-label", "Page");
    const of = document.createElement("span");
    of.textContent = `of ${pages[pages.length - 1]}`;
    const next = document.createElement("button");
    next.type = "button";
    next.className = "pager-step";
    next.dataset.dir = "1";
    next.setAttribute("aria-label", "Next page");
    next.textContent = "›";
    const sheet = document.createElement("span");
    sheet.className = "pager-sheet";
    sheet.id = "pager-sheet";
    root.append(prev, field, of, next, sheet);
    const go = (pageNumber) => {
      if (!pages.includes(pageNumber)) {
        field.value = String(state.visiblePage || pages[0]);
        return;
      }
      scrollToPage(pageNumber);
    };
    prev.addEventListener("click", () => {
      const index = pages.indexOf(state.visiblePage || pages[0]);
      if (index > 0) go(pages[index - 1]);
    });
    next.addEventListener("click", () => {
      const index = pages.indexOf(state.visiblePage || pages[0]);
      if (index >= 0 && index < pages.length - 1) go(pages[index + 1]);
    });
    field.addEventListener("change", () => go(Number(field.value)));
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        go(Number(field.value));
      }
    });
    syncPager();
  }

  function renderLists() {
    renderIndex(currentRun());
  }

  function chunkSearchText(chunk) {
    const metadata = chunk.metadata || {};
    return [
      chunk.chunk_id,
      metadata.record_type,
      metadata.record_label,
      metadata.cd_detail_title,
      metadata.cd_sheet_number,
      metadata.cd_sheet_title,
      metadata.cd_description,
    ].filter(Boolean).join(" ").toLowerCase();
  }

  function renderIndex(run) {
    const root = document.getElementById("chunk-index");
    if (!root) return;
    root.replaceChildren();
    const groups = new Map();
    for (const chunk of run.document.chunks) {
      const recordType = chunk.metadata?.record_type || "chunk";
      if (!groups.has(recordType)) groups.set(recordType, []);
      groups.get(recordType).push(chunk);
    }
    const ordered = [...groups.entries()].sort((left, right) => right[1].length - left[1].length);
    for (const [recordType, chunks] of ordered) {
      const group = document.createElement("section");
      group.className = "index-group";
      const summary = document.createElement("h4");
      summary.className = "index-label";
      summary.textContent = recordType;
      const count = document.createElement("span");
      count.textContent = String(chunks.length);
      summary.appendChild(count);
      group.appendChild(summary);
      const list = document.createElement("div");
      list.className = "list";
      for (const chunk of chunks) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.kind = "chunk";
        button.dataset.id = chunk.chunk_id;
        button.dataset.search = chunkSearchText(chunk);
        const metadata = chunk.metadata || {};
        button.textContent = [
          metadata.cd_sheet_number,
          metadata.record_label || metadata.cd_detail_title || chunk.chunk_id,
        ].filter(Boolean).join(" · ");
        button.addEventListener("click", () => {
          select("chunk", chunk.chunk_id);
          scrollToPage(chunk.page_start);
        });
        list.appendChild(button);
      }
      group.appendChild(list);
      root.appendChild(group);
    }
  }

  function filterIndex(query) {
    const needle = query.trim().toLowerCase();
    document.querySelectorAll("#chunk-index .index-group").forEach((group) => {
      let shown = 0;
      group.querySelectorAll("button").forEach((button) => {
        const match = !needle || (button.dataset.search || "").includes(needle);
        button.hidden = !match;
        if (match) shown += 1;
      });
      group.hidden = shown === 0;
    });
  }

  function renderIssues() {
    const run = currentRun();
    const root = document.getElementById("issues");
    if (!root) return;
    root.replaceChildren();
    if (!run.issues.length) return;
    const count = document.createElement("p");
    count.className = "issue-count";
    count.textContent = `${run.issues.length} issue${run.issues.length === 1 ? "" : "s"}`;
    root.appendChild(count);
    for (const issue of run.issues) {
      const row = document.createElement("div");
      row.className = `issue ${issue.severity}`;
      row.textContent = `[${issue.code}] ${issue.message}`;
      root.appendChild(row);
    }
  }

  function renderStats() {
    const run = currentRun();
    const root = document.getElementById("counts");
    if (!root) return;
    const stats = run.stats;
    root.replaceChildren();
    root.textContent = [
      `${stats.page_count} pages`,
      `${stats.block_count} blocks`,
      `${stats.chunk_count} chunks`,
      `${stats.figure_count} figures`,
    ].join(" · ");
  }

  function swatch(origin) {
    const mark = document.createElement("i");
    mark.className = keyClass(origin);
    return mark;
  }

  function pipelineKeyValue(item) {
    const parts = [String(item.chunks)];
    if (item.values) {
      parts.push(Object.entries(item.values).map(([name, count]) => `${name} ${count}`).join(", "));
    } else if (item.record_types && item.record_types.length) {
      parts.push(item.record_types.join(", "));
    }
    return parts.join(" · ");
  }

  function mapDisclosure(className, title, titleClass) {
    const box = document.createElement("details");
    box.className = className;
    const summary = document.createElement("summary");
    summary.className = titleClass;
    summary.textContent = title;
    box.appendChild(summary);
    return box;
  }

  function mapBox(title, columns) {
    const box = mapDisclosure("map-box", title, "map-title");
    mapCols(box, columns, "default");
    return box;
  }

  function mapCols(parent, columns, origin = "default") {
    if (!columns.length) return;
    const list = document.createElement("ul");
    list.className = "map-cols";
    for (const column of columns) {
      const item = document.createElement("li");
      item.className = keyClass(origin);
      item.textContent = column;
      list.appendChild(item);
    }
    parent.appendChild(list);
  }

  function mapNest(parent, title, columns, origin = "default") {
    const nest = mapDisclosure(
      origin === "pipeline" ? "map-nest pipeline" : "map-nest",
      title,
      keyClass(origin),
    );
    mapCols(nest, columns, origin);
    parent.appendChild(nest);
    return nest;
  }

  function mapValueKeys(parent, value, origin) {
    if (!value || typeof value !== "object") return;
    const source = Array.isArray(value) ? value.find((item) => item && typeof item === "object") : value;
    if (!source || typeof source !== "object" || Array.isArray(source)) return;
    const scalars = [];
    const nested = [];
    for (const [key, item] of Object.entries(source)) {
      const records = Array.isArray(item) && item.some((entry) => entry && typeof entry === "object");
      if (records || (item && typeof item === "object" && !Array.isArray(item))) nested.push([key, item]);
      else scalars.push(key);
    }
    mapCols(parent, scalars.sort((left, right) => left.localeCompare(right)), origin);
    nested.sort((left, right) => left[0].localeCompare(right[0]));
    for (const [key, item] of nested) mapValueKeys(mapNest(parent, key, [], origin), item, origin);
  }

  function mapEdge(label) {
    const edge = document.createElement("p");
    edge.className = "map-edge";
    edge.textContent = label;
    return edge;
  }

  function renderSchemaMap(parent, schema) {
    const tables = schema.tables || {};
    const map = document.createElement("figure");
    map.className = "schema-map";

    const header = mapBox("vera_metadata", tables.vera_metadata || ["key", "value"]);
    const archive = mapNest(header, "archive_metadata", []);
    mapValueKeys(archive, schema.convert_keys || {}, "default");
    mapValueKeys(archive, schema.caller_keys || {}, "pipeline");
    map.appendChild(header);
    map.appendChild(mapEdge("*_attachment_id → attachment_id"));

    const attachments = mapBox("attachments", tables.attachments || ["attachment_id"]);
    mapNest(attachments, "viewer_blocks", [
      "block_id", "page_number", "block_type", "text", "bbox", "heading_level", "sort_order",
    ]);
    map.appendChild(attachments);
    map.appendChild(mapEdge("regions.block_id → block_id · many → one"));

    const chunks = mapBox("chunks", tables.chunks || ["chunk_id", "text", "metadata_json"]);
    const metadata = mapNest(chunks, "metadata_json", []);
    mapCols(metadata, (schema.base_chunk_keys || []).filter((key) => key !== "regions"), "default");
    const pipeline = schema.pipeline || {};
    const pipelineKeys = (pipeline.keys || []).map((item) => item.key);
    if (pipelineKeys.length) {
      const label = [pipeline.name, pipeline.version].filter(Boolean).join(" ");
      mapNest(metadata, label || "pipeline", pipelineKeys, "pipeline");
    }
    const regionKeys = schema.region_keys || ["block_id", "page_number", "bbox"];
    const regions = mapNest(metadata, "regions", []);
    mapCols(regions, regionKeys.filter((key) => DEFAULT_REGION_KEYS.has(key)), "default");
    mapCols(regions, regionKeys.filter((key) => !DEFAULT_REGION_KEYS.has(key)), "pipeline");
    const contained = document.createElement("p");
    contained.className = "map-note";
    contained.textContent = "1 chunk → many regions";
    regions.appendChild(contained);
    map.appendChild(chunks);
    map.appendChild(mapEdge("embeddings.chunk_id → chunks.chunk_id · many → one"));
    map.appendChild(mapBox("embeddings", tables.embeddings || ["chunk_id"]));
    map.appendChild(mapEdge("chunk_id → chunks · attachment_id → attachments · many ↔ many"));
    map.appendChild(mapBox("chunk_attachments", tables.chunk_attachments || ["chunk_id", "attachment_id", "role"]));
    map.appendChild(mapEdge("chunks_fts.chunk_id → chunks.chunk_id · one → one"));
    map.appendChild(mapBox("chunks_fts", tables.chunks_fts || ["chunk_id", "text"]));

    parent.appendChild(map);
  }

  function renderArchive() {
    const run = currentRun();
    const root = document.getElementById("archive");
    if (!root) return;
    root.replaceChildren();
    const schema = run.document.schema || {};
    const legend = document.createElement("p");
    legend.className = "key-legend";
    legend.append(swatch("default"), document.createTextNode(" default "), swatch("pipeline"), document.createTextNode(" pipeline"));
    root.appendChild(legend);
    const caller = new Set(Object.keys(schema.caller_keys || {}));
    const base = new Set(schema.base_chunk_keys || []);
    const header = appendStore(root, "vera_metadata", {
      rows: Object.entries(schema.format_keys || {}),
      origin: "default",
    });
    const archiveRows = [
      ...Object.entries(schema.convert_keys || {}),
      ...Object.entries(schema.caller_keys || {}),
    ].sort((left, right) => left[0].localeCompare(right[0]));
    appendStore(header, "archive_metadata", {
      nested: true,
      rows: archiveRows,
      origin: (key) => (caller.has(key) ? "pipeline" : "default"),
    });

    const pipeline = schema.pipeline || {};
    const metadataRows = (pipeline.keys || []).map((item) => [item.key, pipelineKeyValue(item)]);
    const baseNames = (schema.base_chunk_keys || []).filter((key) => key !== "regions");
    const chunks = appendStore(root, "chunks", {
      names: ["chunk_id", "text", "created_at", "updated_at"],
      origin: "default",
    });
    const metadata = appendStore(chunks, "metadata_json", {
      nested: true,
      names: baseNames,
      rows: metadataRows,
      origin: (key) => (base.has(key) ? "default" : "pipeline"),
    });
    if ((schema.region_keys || []).length) {
      appendStore(metadata, "regions", {
        nested: true,
        names: schema.region_keys,
        origin: (key) => (DEFAULT_REGION_KEYS.has(key) ? "default" : "pipeline"),
      });
    }

    const tables = schema.tables || {};
    for (const name of Object.keys(tables)) {
      if (name === "vera_metadata" || name === "chunks") continue;
      appendStore(root, name, { names: tables[name] || [] });
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

  function renderMap() {
    const root = document.getElementById("schema-map");
    if (!root) return;
    root.replaceChildren();
    const schema = currentRun().document.schema || {};
    const legend = document.createElement("p");
    legend.className = "key-legend";
    legend.append(swatch("default"), document.createTextNode(" default "), swatch("pipeline"), document.createTextNode(" pipeline"));
    root.appendChild(legend);
    renderSchemaMap(root, schema);
  }

  function renderAll() {
    renderHeader();
    renderArchive();
    renderMap();
    renderPager();
    renderPages();
    renderLists();
    renderIssues();
    renderStats();
    renderCompare();
    renderDetail();
  }

  document.querySelectorAll(".inspector-tabs button").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  const indexFilter = document.getElementById("index-filter");
  if (indexFilter) {
    indexFilter.addEventListener("input", () => filterIndex(indexFilter.value));
  }

  document.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      const layer = input.getAttribute("data-layer");
      body.classList.toggle(`show-${layer}`, input.checked);
    });
  });

  renderAll();
})();
