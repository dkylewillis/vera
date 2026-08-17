const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const defaultSidecar = process.platform === "win32"
  ? path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar.exe")
  : path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar");
const sidecarPath = process.env.VERA_SIDECAR_EXE || defaultSidecar;

if (!fs.existsSync(sidecarPath)) {
  console.error(`Packaged sidecar not found: ${sidecarPath}`);
  process.exit(1);
}

const child = spawn(sidecarPath, [], {
  cwd: path.dirname(sidecarPath),
  stdio: ["pipe", "pipe", "inherit"],
  windowsHide: true,
});

let buffer = "";
let settled = false;

function finish(code, message) {
  if (settled) return;
  settled = true;
  if (message) console.error(message);
  child.kill();
  process.exit(code);
}

const timer = setTimeout(() => {
  finish(1, "Timed out waiting for describe_ingest_pipelines");
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
    if (payload.id !== "describe-1") continue;
    clearTimeout(timer);
    if (!payload.ok) {
      finish(1, payload.error || "describe_ingest_pipelines failed");
      return;
    }
    const providers = (payload.result?.pipelines || []).map((item) => item.provider || item.spec);
    const missing = ["pymupdf", "docling"].filter((name) => !providers.includes(name));
    if (missing.length) {
      finish(1, `Sidecar omitted ingest providers: ${missing.join(", ")} (got ${providers.join(", ") || "none"})`);
      return;
    }
    console.log(JSON.stringify({
      sidecar: sidecarPath,
      providers,
    }, null, 2));
    finish(0);
  }
});

child.stdin.write(`${JSON.stringify({ id: "describe-1", action: "describe_ingest_pipelines" })}\n`);
