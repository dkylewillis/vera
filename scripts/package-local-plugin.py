"""Stage the local-only Codex plugin without a remotely discovered .app.json."""

import argparse
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New generated plugin directory outside this repository (named vera)",
    )
    parser.add_argument("--mcp-command", help="Absolute installed vera-mcp executable")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    dest = args.output_dir.expanduser().resolve()
    if dest == root or root in dest.parents:
        parser.error("--output-dir must be outside this repository")
    if dest.name != "vera":
        parser.error("--output-dir must end in vera to match the plugin name")
    if dest.exists():
        parser.error("--output-dir must be new; existing packages are never merged")
    if args.mcp_command and not Path(args.mcp_command).is_file():
        parser.error("--mcp-command must name an existing executable")
    plugin_root = root / "plugins" / "vera"
    shutil.copytree(plugin_root, dest)
    if args.mcp_command:
        config_path = dest / ".mcp.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["mcpServers"]["vera"]["command"] = str(Path(args.mcp_command).resolve())
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
