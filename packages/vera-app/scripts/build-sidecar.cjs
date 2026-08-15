const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appDir, "..", "..");
const tessdata = path.join(repoRoot, "packages", "vera-ingest-pymupdf", "src", "vera_ingest_pymupdf", "tessdata");
const entry = path.join("src", "vera_app", "sidecar.py");

const pyinstallerArgs = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--add-data",
  `${tessdata}${path.delimiter}vera_ingest_pymupdf/tessdata`,
  // Keep dist-info so importlib.metadata can still see vera.ingest_pipelines
  // when the freeze does not rely solely on import-time registration.
  "--copy-metadata",
  "vera-ingest-pymupdf",
  "--copy-metadata",
  "vera-ingest",
  "--hidden-import",
  "vera_ingest_pymupdf",
  // Keep optional ML stacks out of the freeze even when the build venv has
  // `--extra ml`. Sentence Transformers is imported lazily and must not land
  // in packaged sidecars.
  "--exclude-module",
  "torch",
  "--exclude-module",
  "torchgen",
  "--exclude-module",
  "sentence_transformers",
  "--exclude-module",
  "transformers",
  "--name",
  "vera-sidecar",
  "--distpath",
  "build/sidecar",
  "--workpath",
  "build/pyinstaller",
  "--specpath",
  "build/pyinstaller",
  entry,
];

// PyInstaller analyzes imports, so the sidecar and document packages must be importable.
const sourcePaths = [
  path.join(repoRoot, "packages", "vera-app", "src"),
  path.join(repoRoot, "packages", "vera-doc", "src"),
  path.join(repoRoot, "packages", "vera-ingest", "src"),
  path.join(repoRoot, "packages", "vera-ingest-pymupdf", "src"),
];
const env = {
  ...process.env,
  PYTHONPATH: [...sourcePaths, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
};

function venvPython() {
  const configured = process.env.VERA_SIDECAR_PYTHON || process.env.VERA_APP_PYTHON;
  if (configured) return configured;
  const candidate =
    process.platform === "win32"
      ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
      : path.join(repoRoot, ".venv", "bin", "python");
  return fs.existsSync(candidate) ? candidate : null;
}

function hasPyInstaller(python) {
  const probe = spawnSync(python, ["-c", "import PyInstaller"], { env, stdio: "ignore" });
  return probe.status === 0;
}

function run(command, args, label) {
  console.log(`Building VERA sidecar with ${label}`);
  return spawnSync(command, args, { cwd: appDir, stdio: "inherit", shell: false, env });
}

if (!fs.existsSync(tessdata)) {
  console.error(`Missing bundled OCR data: ${tessdata}`);
  process.exit(1);
}

const python = venvPython();
let result;
if (python && hasPyInstaller(python)) {
  // Preferred: the project virtualenv directly. Avoids `uv run`, which installs
  // console-script launchers that Windows antivirus/EDR can block while uv
  // rewrites their PE resources.
  result = run(python, pyinstallerArgs, python);
} else {
  const uvArgs = ["run", "--project", repoRoot, "--extra", "app", "--extra", "sidecar", "python", ...pyinstallerArgs];
  result = run("uv", uvArgs, "uv run");
  if (result.error || (result.status ?? 1) !== 0) {
    console.error(
      "\nSidecar build failed. If uv reported 'Failed to update Windows PE resources',\n" +
        "install PyInstaller into the project virtualenv and retry:\n" +
        "  uv pip install \"pyinstaller>=6\"\n" +
        "  npm run build:sidecar\n",
    );
  }
}

process.exit(result.status ?? 1);
