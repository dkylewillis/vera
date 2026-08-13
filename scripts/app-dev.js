const { spawnSync } = require("child_process");
const path = require("path");

// `uv run` spawns its command via Rust's std::process::Command, which does
// not consult PATHEXT on Windows: it needs the literal `npm.cmd` shim there,
// while POSIX systems only ship the extensionless `npm` script.
// https://github.com/astral-sh/uv/issues/8770
const npmBin = process.platform === "win32" ? "npm.cmd" : "npm";

const repoRoot = path.resolve(__dirname, "..");

const result = spawnSync(
  "uv",
  [
    "run",
    "--extra",
    "app",
    "--extra",
    "ml",
    "--extra",
    "docling",
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
