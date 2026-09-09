"""Offline MCP discovery contract checks."""

from mcp_server import build_mcp_app, mcp


def test_mcp_exposes_read_only_market_tools_and_methodology():
    assert set(mcp._tool_manager._tools) == {
        "search_catalog", "search_cpv", "price_variance", "market_overview",
        "list_watchlists", "scan_run_status",
    }
    for tool in mcp._tool_manager._tools.values():
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
    assert "fastcpi://methodology" in {str(uri) for uri in mcp._resource_manager._resources}


def test_mcp_streamable_http_is_mounted_at_subapp_root():
    paths = {getattr(route, "path", None) for route in build_mcp_app().routes}
    assert "/" in paths
    assert "/.well-known/oauth-protected-resource/mcp/" in paths
