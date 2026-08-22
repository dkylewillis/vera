const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const defaultSidecar = process.platform === "win32"
  ? path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar.exe")
  : path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar");

const REQUIRED_MINILM_FILES = ["config.json", "model.onnx", "tokenizer.json"];

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

function runDescribeChecks(sidecarPath) {
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
  }, 60_000);

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
      finish(1, `Sidecar included Docling; 0.3.0 packaged Convert is PyMuPDF-only (got ${providers.join(", ")})`);
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
  defaultSidecar,
  findBundledMinilm,
  minilmCandidates,
};

if (require.main === module) {
  main();
}
