const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const appDir = path.join(__dirname, "packages", "vera-app");
const args = process.argv.slice(2);
const wantDir = args.includes("--dir");
const filteredArgs = args.filter((arg) => arg !== "--dir");

const outRoot =
  process.env.VERA_DIST_OUTPUT ||
  (process.platform === "win32"
    ? path.join(process.env.LOCALAPPDATA || process.env.TEMP || appDir, "Vera", "desktop-release")
    : path.join(appDir, "release"));

fs.rmSync(outRoot, { recursive: true, force: true });
fs.rmSync(path.join(appDir, "release"), { recursive: true, force: true });

const npmArgs = ["run", "dist", "--"];
if (wantDir) npmArgs.push("--dir");
npmArgs.push(`-c.directories.output=${outRoot}`, ...filteredArgs);

console.log(`Packaging VERA to ${outRoot}`);
const result = spawnSync("npm", npmArgs, {
  cwd: appDir,
  stdio: "inherit",
  shell: true,
  env: process.env,
});
process.exit(result.status ?? 1);
