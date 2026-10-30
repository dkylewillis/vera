const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const defaultSidecar = process.platform === "win32"
  ? path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar.exe")
  : path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar");

const REQUIRED_MINILM_FILES = ["config.json", "model.onnx", "tokenizer.json"];
const FORBIDDEN_RUNTIME_PACKAGES = [
  "torch",
  "torchvision",
  "torchaudio",
  "sentence_transformers",
  "transformers",
];

function minilmCandidates(sidecarExe) {
  const sidecarDir = path.dirname(sidecarExe);
  return [
    path.join(sidecarDir, "sentence_transformers_models", "all-MiniLM-L6-v2"),
    path.join(sidecarDir, "_internal", "sentence_transformers_models", "all-MiniLM-L6-v2"),
  ];
}

function findBundledMinilm(sidecarExe) {
  for (const candidate of minilmCandidates(sidecarExe)) {
    if (REQUIRED_MINILM_FILES.every((name) => fs.existsSync(path.join(candidate, name)))) {
      return candidate;
    }
  }
  return null;
}

function findForbiddenRuntime(sidecarExe) {
  const sidecarDir = path.dirname(sidecarExe);
  const roots = [sidecarDir, path.join(sidecarDir, "_internal")];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const name of FORBIDDEN_RUNTIME_PACKAGES) {
      const candidate = path.join(root, name);
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return null;
}

function runDescribeChecks(sidecarPath) {
  const forbidden = findForbiddenRuntime(sidecarPath);
  if (forbidden) {
    console.error(
      "Packaged sidecar must not include Torch / Sentence Transformers. Found:\n  " + forbidden,
    );
    process.exit(1);
  }

  const minilmPath = findBundledMinilm(sidecarPath);
  if (!minilmPath) {
    console.error(
      "Packaged sidecar is missing vendored MiniLM weights. Looked in:\n  "
        + minilmCandidates(sidecarPath).join("\n  "),
    );
    process.exit(1);
  }

  const child = spawn(sidecarPath, [], {
    cwd: path.dirname(sidecarPath),
    stdio: ["pipe", "pipe", "inherit"],
    windowsHide: true,
    env: {
      ...process.env,
      VERA_ONNX_MINILM_HOME: path.dirname(minilmPath),
      VERA_SENTENCE_TRANSFORMERS_HOME: path.dirname(minilmPath),
    },
  });

  let buffer = "";
  let settled = false;
  const pending = new Map();

  function finish(code, message) {
    if (settled) return;
    settled = true;
    if (message) console.error(message);
    child.kill();
    process.exit(code);
  }

  const timer = setTimeout(() => {
    finish(1, "Timed out waiting for packaged sidecar describe checks");
  }, 120_000);

  child.on("error", (error) => {
    clearTimeout(timer);
    finish(1, error.message);
  });

  child.on("exit", (code) => {
    if (!settled) {
      clearTimeout(timer);
      finish(code ?? 1, `Sidecar exited before answering (code ${code})`);
    }
  });

  function send(id, action) {
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      child.stdin.write(`${JSON.stringify({ id, action })}\n`);
    });
  }

  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let payload;
      try {
        payload = JSON.parse(line);
      } catch {
        continue;
      }
      const waiter = pending.get(payload.id);
      if (!waiter) continue;
      pending.delete(payload.id);
      waiter.resolve(payload);
    }
  });

  (async () => {
    const pipelines = await send("describe-1", "describe_ingest_pipelines");
    if (!pipelines.ok) {
      finish(1, pipelines.error || "describe_ingest_pipelines failed");
      return;
    }
    const providers = (pipelines.result?.pipelines || []).map((item) => item.provider || item.spec);
    if (!providers.includes("pymupdf")) {
      finish(1, `Sidecar omitted ingest provider pymupdf (got ${providers.join(", ") || "none"})`);
      return;
    }
    if (providers.includes("docling")) {
      finish(1, `Sidecar included Docling; 0.3.x packaged Convert is PyMuPDF-only (got ${providers.join(", ")})`);
      return;
    }

    const embedders = await send("describe-2", "describe_embedding_providers");
    if (!embedders.ok) {
      finish(1, embedders.error || "describe_embedding_providers failed");
      return;
    }
    const embedderNames = (embedders.result?.providers || []).map((item) => item.provider);
    if (!embedderNames.includes("sentence-transformers")) {
      finish(1, `Sidecar omitted sentence-transformers (got ${embedderNames.join(", ") || "none"})`);
      return;
    }
    if (!embedderNames.includes("openai")) {
      finish(1, `Sidecar omitted openai embedder (got ${embedderNames.join(", ") || "none"})`);
      return;
    }

    await smokeAgentService(sidecarPath);

    console.log(JSON.stringify({
      sidecar: sidecarPath,
      providers,
      embedders: embedderNames,
      minilm: minilmPath,
    }, null, 2));
    clearTimeout(timer);
    finish(0);
  })().catch((error) => {
    clearTimeout(timer);
    finish(1, error instanceof Error ? error.message : String(error));
  });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : 0;
      probe.close(() => resolve(port));
    });
  });
}

function httpRequest(options, body) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        resolve({
          status: res.statusCode || 0,
          headers: res.headers,
          body: Buffer.concat(chunks).toString("utf8"),
        });
      });
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function stopProcessTree(child) {
  if (!child || !child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true });
    return;
  }
  child.kill("SIGKILL");
}

async function waitForHealth(port) {
  const deadline = Date.now() + 30_000;
  let lastError = "service did not answer /healthz";
  while (Date.now() < deadline) {
    try {
      const health = await httpRequest({
        hostname: "127.0.0.1",
        port,
        path: "/healthz",
        method: "GET",
        timeout: 2000,
      });
      if (health.status === 200) {
        const payload = JSON.parse(health.body);
        if (payload.ok === true && payload.version) return payload;
        lastError = `unexpected health payload: ${health.body}`;
      } else {
        lastError = `healthz status ${health.status}`;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(lastError);
}

async function smokeAgentService(sidecarPath) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "vera-service-"));
  const library = path.join(root, "library");
  fs.mkdirSync(library);
  const policyPath = path.join(root, "policy.json");
  fs.writeFileSync(
    policyPath,
    JSON.stringify({
      library_roots: [library],
      disclosure: "Packaged sidecar smoke check.",
    }),
  );
  const port = await freePort();
  const token = "packaged-smoke-token";
  const child = spawn(
    sidecarPath,
    ["mcp-service", "--policy", policyPath, "--port", String(port)],
    {
      cwd: path.dirname(sidecarPath),
      stdio: ["ignore", "ignore", "pipe"],
      windowsHide: true,
      env: { ...process.env, VERA_SERVICE_TOKEN: token },
    },
  );
  let stderr = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  try {
    const health = await waitForHealth(port);
    if (!health.version) throw new Error("healthz omitted version");

    const denied = await httpRequest({
      hostname: "127.0.0.1",
      port,
      path: "/mcp",
      method: "POST",
      timeout: 5000,
    });
    if (denied.status !== 401) {
      throw new Error(`unauthenticated /mcp returned ${denied.status}, expected 401`);
    }

    const initBody = JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "vera-sidecar-smoke", version: "0" },
      },
    });
    const init = await httpRequest(
      {
        hostname: "127.0.0.1",
        port,
        path: "/mcp",
        method: "POST",
        timeout: 10000,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json, text/event-stream",
          "Content-Length": Buffer.byteLength(initBody),
        },
      },
      initBody,
    );
    if (init.status !== 200) {
      throw new Error(`initialize returned ${init.status}: ${init.body.slice(0, 300)}`);
    }
    const sessionId = init.headers["mcp-session-id"];
    if (!sessionId) throw new Error("initialize did not return mcp-session-id");

    const noteBody = JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" });
    await httpRequest(
      {
        hostname: "127.0.0.1",
        port,
        path: "/mcp",
        method: "POST",
        timeout: 10000,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json, text/event-stream",
          "mcp-session-id": Array.isArray(sessionId) ? sessionId[0] : sessionId,
          "Content-Length": Buffer.byteLength(noteBody),
        },
      },
      noteBody,
    );

    const listBody = JSON.stringify({
      jsonrpc: "2.0",
      id: 2,
      method: "tools/list",
      params: {},
    });
    const listed = await httpRequest(
      {
        hostname: "127.0.0.1",
        port,
        path: "/mcp",
        method: "POST",
        timeout: 10000,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json, text/event-stream",
          "mcp-session-id": Array.isArray(sessionId) ? sessionId[0] : sessionId,
          "Content-Length": Buffer.byteLength(listBody),
        },
      },
      listBody,
    );
    if (listed.status !== 200 || !listed.body.includes("vera_library_info")) {
      throw new Error(`tools/list failed (${listed.status}): ${listed.body.slice(0, 300)}`);
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${detail}\n${stderr}`.trim());
  } finally {
    stopProcessTree(child);
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function main() {
  const sidecarPath = process.env.VERA_SIDECAR_EXE || defaultSidecar;
  if (!fs.existsSync(sidecarPath)) {
    console.error(`Packaged sidecar not found: ${sidecarPath}`);
    process.exit(1);
  }
  runDescribeChecks(sidecarPath);
}

module.exports = {
  REQUIRED_MINILM_FILES,
  FORBIDDEN_RUNTIME_PACKAGES,
  defaultSidecar,
  findBundledMinilm,
  findForbiddenRuntime,
  minilmCandidates,
};

if (require.main === module) {
  main();
}
