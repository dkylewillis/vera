/**
 * Smoke-test the packaged sidecar in mcp-bridge mode against a fixture library.
 *
 * Requires VERA_SIDECAR_EXE (or the default build path). Creates a temporary
 * hashing Markdown fixture and a fail-closed policy file.
 */
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const defaultSidecar =
  process.platform === "win32"
    ? path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar.exe")
    : path.join(appDir, "build", "sidecar", "vera-sidecar", "vera-sidecar");

function writeFixtureLibrary(root) {
  fs.mkdirSync(root, { recursive: true });
  const md = path.join(root, "notes.md");
  fs.writeFileSync(
    md,
    "# Bridge fixture\n\nStormwater detention is required when impervious area increases.\n",
    "utf8",
  );
  const archive = path.join(root, "notes.vera");
  const convert = spawnSync(
    process.env.VERA_APP_PYTHON || "python",
    [
      "-c",
      "from vera_ingest import convert; "
        + `convert(r'''${md}''', r'''${archive}''', model='hashing')`,
    ],
    { encoding: "utf8" },
  );
  if (convert.status !== 0) {
    throw new Error(
      `Unable to convert bridge fixture:\n${convert.stderr || convert.stdout || "unknown error"}`,
    );
  }
  const policyPath = path.join(root, "policy.json");
  fs.writeFileSync(
    policyPath,
    JSON.stringify({ library_root: root, max_top_k: 5, max_context_chunks: 1 }, null, 2),
    "utf8",
  );
  return { policyPath, archive };
}

function main() {
  const sidecarPath = process.env.VERA_SIDECAR_EXE || defaultSidecar;
  if (!fs.existsSync(sidecarPath)) {
    console.error(`Packaged sidecar not found: ${sidecarPath}`);
    process.exit(1);
  }

  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), "vera-bridge-verify-"));
  const workCwd = fs.mkdtempSync(path.join(os.tmpdir(), "vera bridge cwd "));
  let policyPath;
  let archive;
  try {
    ({ policyPath, archive } = writeFixtureLibrary(fixtureRoot));
  } catch (error) {
    console.error(String(error));
    process.exit(1);
  }

  const env = {
    PATH: process.env.PATH,
    SYSTEMROOT: process.env.SYSTEMROOT,
    WINDIR: process.env.WINDIR,
    TEMP: process.env.TEMP,
    TMP: process.env.TMP,
    VERA_BRIDGE_POLICY_PATH: policyPath,
    VERA_AUTO_INSTALL_SEMANTIC_DEPS: "0",
  };

  const child = spawn(sidecarPath, ["mcp-bridge"], {
    cwd: workCwd,
    env,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });

  let stdout = "";
  let stderr = "";
  let finished = false;
  const finish = (code, message) => {
    if (finished) return;
    finished = true;
    if (message) console.error(message);
    try {
      child.kill();
    } catch (_) {
      /* ignore */
    }
    process.exit(code);
  };

  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString("utf8");
    if (stdout.includes('"id":1') || stdout.includes('"id": 1')) {
      console.log(
        JSON.stringify({
          ok: true,
          sidecar: sidecarPath,
          archive,
          note: "mcp-bridge initialized from unrelated cwd",
        }),
      );
      finish(0);
    }
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });
  child.on("error", (error) => finish(1, String(error)));
  child.on("exit", (code) => {
    if (!finished) {
      finish(code || 1, stderr || `mcp-bridge exited with ${code}`);
    }
  });

  setTimeout(() => finish(1, `Timed out waiting for mcp-bridge. stderr:\n${stderr}`), 20000);

  const message = {
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "vera-bridge-verify", version: "0.0.0" },
    },
  };
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

main();
