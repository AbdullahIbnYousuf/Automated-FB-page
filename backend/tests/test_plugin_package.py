"""Prevent the desktop loader from silently dropping the private MCP server."""

import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[2] / "plugins" / "the-test-lab-operations"


def test_compatibility_manifest_is_not_masked_by_portable_manifest():
    assert not (PACKAGE / "plugin.json").exists()
    assert not (PACKAGE / "mcp.json").exists()
    manifest = json.loads((PACKAGE / ".codex-plugin/plugin.json").read_text())
    assert manifest["name"] == PACKAGE.name
    assert manifest["version"] == "0.1.1"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert (PACKAGE / "skills/facebook-scheduling/SKILL.md").is_file()


def test_native_http_server_uses_discovered_oauth_without_embedded_credentials():
    config = json.loads((PACKAGE / ".mcp.json").read_text())
    assert config == {"mcpServers": {"the-test-lab-operations": {
        "type": "http",
        "url": "https://facebook-page-operations-api.onrender.com/mcp",
        "scopes": ["email"],
    }}}
