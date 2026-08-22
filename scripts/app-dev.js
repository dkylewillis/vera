const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

// `uv run` spawns its command via Rust's std::process::Command, which does
// not consult PATHEXT on Windows: it needs the literal `npm.cmd` shim there,
// while POSIX systems only ship the extensionless `npm` script.
// https://github.com/astral-sh/uv/issues/8770
const npmBin = process.platform === "win32" ? "npm.cmd" : "npm";

const repoRoot = path.resolve(__dirname, "..");
const minilmDest = path.join(
  repoRoot,
  "packages",
  "vera-app",
  "build",
  "minilm",
  "all-MiniLM-L6-v2",
);
const vendorScript = path.join(
  repoRoot,
  "packages",
  "vera-app",
  "scripts",
  "vendor_minilm.py",
);

function runUv(args, extra) {
  return spawnSync("uv", ["run", "--extra", extra, ...args], {
    cwd: repoRoot,
    stdio: "inherit",
    shell: true,
    env: process.env,
  });
}

function snapshotReady() {
  return (
    fs.existsSync(path.join(minilmDest, "model.onnx")) &&
    fs.existsSync(path.join(minilmDest, "tokenizer.json"))
  );
}

function vendorMinilm(extra) {
  console.log(`Vendoring MiniLM ONNX snapshot with --extra ${extra}`);
  return runUv(["python", vendorScript, "--dest", minilmDest], extra);
}

if (!snapshotReady()) {
  let vendor = vendorMinilm("onnx");
  if ((vendor.status ?? 1) !== 0 || !snapshotReady()) {
    console.warn(
      "MiniLM ONNX snapshot missing; exporting once with --extra ml (Sentence Transformers is build-time only).",
    );
    vendor = vendorMinilm("ml");
  }
  if ((vendor.status ?? 1) !== 0 || !snapshotReady()) {
    console.error(
      "app:dev needs a MiniLM ONNX graph at packages/vera-app/build/minilm/all-MiniLM-L6-v2/model.onnx.\n" +
        "Export once, then retry:\n" +
        "  uv run --extra ml python packages/vera-app/scripts/export_minilm_onnx.py --dest packages/vera-app/build/minilm-export/all-MiniLM-L6-v2\n" +
        "  uv run --extra onnx python packages/vera-app/scripts/vendor_minilm.py --dest packages/vera-app/build/minilm/all-MiniLM-L6-v2",
    );
    process.exit(vendor.status ?? 1);
  }
}

const result = spawnSync(
  "uv",
  [
    "run",
    "--extra",
    "app",
    "--extra",
    "onnx",
    npmBin,
    "--prefix",
    "packages/vera-app",
    "run",
    "dev",
  ],
  {
    cwd: repoRoot,
    stdio: "inherit",
    shell: true,
    env: process.env,
  }
);
process.exit(result.status ?? 1);
