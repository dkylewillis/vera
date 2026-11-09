const fs = require("fs");
const path = require("path");

/** Fill empty keys from a dotenv file. Existing non-empty values stay. */
function applyEnvText(env, text) {
  for (const rawLine of String(text).split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const body = line.startsWith("export ") ? line.slice(7).trim() : line;
    const eq = body.indexOf("=");
    if (eq <= 0) continue;
    const key = body.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
    let value = body.slice(eq + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    if (!value) continue;
    const current = env[key];
    if (typeof current === "string" && current.trim()) continue;
    env[key] = value;
  }
  return env;
}

function loadRepoEnv(env, repoRoot) {
  const file = path.join(repoRoot, ".env");
  if (!fs.existsSync(file)) return env;
  return applyEnvText(env, fs.readFileSync(file, "utf8"));
}

module.exports = { applyEnvText, loadRepoEnv };
