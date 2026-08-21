const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const appDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appDir, "..", "..");
const tessdata = path.join(repoRoot, "packages", "vera-ingest-pymupdf", "src", "vera_ingest_pymupdf", "tessdata");
const minilmDir = path.join(appDir, "build", "minilm", "all-MiniLM-L6-v2");
const vendorMinilm = path.join(appDir, "scripts", "vendor_minilm.py");
const entry = path.join("src", "vera_app", "sidecar.py");
const hooksDir = path.join(appDir, "scripts", "hooks");
const workpath = path.join(appDir, "build", "pyinstaller");
const REQUIRED_MINILM_FILES = ["config.json", "modules.json", "model.safetensors", "tokenizer.json"];

const pyinstallerArgs = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--add-data",
  `${tessdata}${path.delimiter}vera_ingest_pymupdf/tessdata`,
  "--add-data",
  `${minilmDir}${path.delimiter}sentence_transformers_models/all-MiniLM-L6-v2`,
  "--additional-hooks-dir",
  hooksDir,
  // Keep dist-info so importlib.metadata can still see vera.ingest_pipelines
  // when the freeze does not rely solely on import-time registration.
  "--copy-metadata",
  "vera-ingest-pymupdf",
  "--copy-metadata",
  "vera-ingest",
  "--copy-metadata",
  "sentence-transformers",
  "--hidden-import",
  "vera_ingest_pymupdf",
  "--hidden-import",
  "sentence_transformers",
  "--collect-all",
  "torch",
  "--collect-all",
  "sentence_transformers",
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

const CRITICAL_MISSING_PREFIXES = [
  "vera_ingest_pymupdf",
  "torch",
  "sentence_transformers",
];

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

function warnFilePath() {
  const candidates = [
    path.join(workpath, "vera-sidecar", "warn-vera-sidecar.txt"),
    path.join(workpath, "warn-vera-sidecar.txt"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[0];
}

function missingModuleName(line) {
  const match = line.match(/missing module named ['"]?([A-Za-z0-9_.]+)/i);
  return match ? match[1] : null;
}

function isCriticalMissing(moduleName) {
  return CRITICAL_MISSING_PREFIXES.includes(moduleName);
}

function failOnCriticalMissingImports() {
  const warnPath = warnFilePath();
  if (!fs.existsSync(warnPath)) {
    console.error(`PyInstaller warning file missing: ${warnPath}`);
    process.exit(1);
  }
  const critical = fs
    .readFileSync(warnPath, "utf8")
    .split(/\r?\n/)
    .map((line) => missingModuleName(line))
    .filter((name) => name && isCriticalMissing(name));
  const unique = [...new Set(critical)].sort();
  if (unique.length) {
    console.error("Sidecar freeze is missing required imports:\n  " + unique.join("\n  "));
    console.error(`See ${warnPath}`);
    process.exit(1);
  }
}

if (!fs.existsSync(tessdata)) {
  console.error(`Missing bundled OCR data: ${tessdata}`);
  process.exit(1);
}

const python = venvPython();

function missingFiles(directory, files) {
  return files.filter((name) => !fs.existsSync(path.join(directory, name)));
}

function assertSnapshot(directory, files, label) {
  const missing = missingFiles(directory, files);
  if (missing.length) {
    console.error(`${label} snapshot is incomplete in ${directory}: missing ${missing.join(", ")}`);
    process.exit(1);
  }
}

function runVendor(command, args, dest, label) {
  console.log(`Vendoring ${label} into ${dest}`);
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: "inherit",
    shell: false,
    env,
  });
  if ((result.status ?? 1) !== 0) {
    console.error(`Failed to vendor ${label} for the sidecar freeze.`);
    process.exit(result.status ?? 1);
  }
}

function vendorWithPython(pythonBin, script, dest, label) {
  runVendor(pythonBin, [script, "--dest", dest], dest, label);
}

function vendorWithUv(script, dest, label) {
  runVendor(
    "uv",
    ["run", "--project", repoRoot, "--extra", "ml", "python", script, "--dest", dest],
    dest,
    label,
  );
}

function vendorSidecarModels(pythonBin) {
  if (pythonBin) {
    vendorWithPython(pythonBin, vendorMinilm, minilmDir, "MiniLM weights");
  } else {
    vendorWithUv(vendorMinilm, minilmDir, "MiniLM weights");
  }
  assertSnapshot(minilmDir, REQUIRED_MINILM_FILES, "MiniLM");
}

vendorSidecarModels(python);

let result;
if (python && hasPyInstaller(python)) {
  // Preferred: the project virtualenv directly. Avoids `uv run`, which installs
  // console-script launchers that Windows antivirus/EDR can block while uv
  // rewrites their PE resources.
  result = run(python, pyinstallerArgs, python);
} else {
  const uvArgs = [
    "run",
    "--project",
    repoRoot,
    "--extra",
    "app",
    "--extra",
    "sidecar",
    "--extra",
    "ml",
    "python",
    ...pyinstallerArgs,
  ];
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

if ((result.status ?? 1) !== 0) {
  process.exit(result.status ?? 1);
}

failOnCriticalMissingImports();
process.exit(0);
