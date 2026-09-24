"""Auto-discovered CRUD roundtrip tests for batch-22-26 stateful servers.

For each server, scan tools.py for create/list tool pairs that share a bucket:
  - a tool that does `local_store.put(_SID, "X", ...)` (create/send/upsert)
  - a tool that does `local_store.list_all(_SID, "X", ...)` (list/search)
When both exist for the same bucket X, we assert:
  invoke create_tool with dummy args → list_tool count increments by exactly 1.

Locks in the write/read pipeline across the whole fleet in one file.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVERS_DIR = REPO_ROOT / "servers"

BATCH_22_26 = {
    "airbyte",
    "airflow",
    "anytype",
    "backblaze",
    "bear",
    "bitwarden",
    "browserbase",
    "cosmosdb",
    "databricks",
    "docker",
    "fivetran",
    "gcs",
    "git-local",
    "google-search",
    "helm",
    "honeycomb",
    "ibm-cloud",
    "jaeger",
    "jina",
    "lastpass",
    "loki",
    "mattermost",
    "minio",
    "onedrive",
    "oracle-cloud",
    "pdf",
    "perplexity",
    "plane",
    "playwright",
    "puppeteer",
    "redshift",
    "rocket-chat",
    "rss",
    "selenium",
    "semgrep",
    "serpapi",
    "shell",
    "shopify",
    "shortcut",
    "snowflake",
    "splunk",
    "ssh",
    "wikipedia",
    "wrike",
    "aws",
    "azure",
    "bigquery",
    "gcp",
    "chrome-devtools",
}


def _extract_pairs(sid: str) -> list[tuple[str, str, str]]:
    """Return (create_tool_name, list_tool_name, bucket) triples for server sid."""
    tools_path = SERVERS_DIR / sid / "tools.py"
    if not tools_path.exists():
        return []
    src = tools_path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    # Find each async function inside register_tools and record buckets it uses.
    creates: dict[str, str] = {}  # func_name -> bucket
    lists: dict[str, str] = {}
    put_pat = re.compile(r'local_store\.put\(\s*_SID\s*,\s*"([^"]+)"')
    list_pat = re.compile(r'local_store\.list_all\(\s*_SID\s*,\s*"([^"]+)"')

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            body_src = ast.get_source_segment(src, node) or ""
            m_put = put_pat.search(body_src)
            m_list = list_pat.search(body_src)
            if m_put:
                creates[node.name] = m_put.group(1)
            if m_list:
                lists[node.name] = m_list.group(1)

    pairs: list[tuple[str, str, str]] = []
    for c_name, c_bucket in creates.items():
        for l_name, l_bucket in lists.items():
            if c_bucket == l_bucket:
                pairs.append((c_name, l_name, c_bucket))
                break
    return pairs


def _discover_all_pairs() -> list[tuple[str, str, str, str]]:
    """Return (sid, create_name, list_name, bucket) for every discovered pair."""
    out = []
    for sid in sorted(BATCH_22_26):
        for c, ln, b in _extract_pairs(sid):
            out.append((sid, c, ln, b))
    return out


PAIRS = _discover_all_pairs()


def _dummy_args(fn) -> dict:
    """Build minimal kwargs to satisfy required params of fn."""
    sig = inspect.signature(fn)
    kwargs = {}
    for pname, p in sig.parameters.items():
        if pname == "self":
            continue
        if p.default is not inspect.Parameter.empty:
            continue
        anno = p.annotation
        anno_str = str(anno).lower() if anno is not inspect.Parameter.empty else "str"
        if "int" in anno_str:
            kwargs[pname] = 1
        elif "bool" in anno_str:
            kwargs[pname] = False
        elif "dict" in anno_str:
            kwargs[pname] = {}
        elif "list" in anno_str:
            kwargs[pname] = []
        else:
            kwargs[pname] = "test-value"
    return kwargs


@pytest.mark.trajectory
@pytest.mark.parametrize(
    "server_id,create_name,list_name,bucket",
    PAIRS,
    ids=[f"{sid}:{c}->{ln}" for sid, c, ln, _ in PAIRS],
)
def test_crud_roundtrip(server_id, create_name, list_name, bucket, tmp_path, monkeypatch):
    """create_* increments list_* count by exactly 1 for shared bucket."""
    import asyncio
    import importlib

    from fastmcp import FastMCP

    monkeypatch.setenv("MCP_OFFLINE", "1")
    monkeypatch.setenv("MCP_STATE_DIR", str(tmp_path))

    from mcp_common import local_store

    mod_name = f"servers.{server_id.replace('-', '_')}.tools"

    async def run():
        # Fresh state, no seed - we want to prove create alone puts a row
        await local_store.reset(server_id)

        tools_mod = importlib.import_module(mod_name)
        m = FastMCP(server_id)
        tools_mod.register_tools(m)
        tools_registry = await m.list_tools()
        by_name = {t.name: t for t in tools_registry}

        assert create_name in by_name, f"{server_id}: create tool {create_name} not registered"
        assert list_name in by_name, f"{server_id}: list tool {list_name} not registered"

        # Baseline count
        before = await local_store.list_all(server_id, bucket)
        base_count = len(before)

        # Invoke create with dummy args
        c_fn = by_name[create_name].fn
        c_kwargs = _dummy_args(c_fn)
        await c_fn(**c_kwargs)

        # Assert bucket grew by 1
        after = await local_store.list_all(server_id, bucket)
        assert len(after) == base_count + 1, (
            f"{server_id}/{bucket}: expected +1 row, got {len(after) - base_count}"
        )

    asyncio.run(run())


def test_crud_pairs_discovered():
    unique_servers = {sid for sid, _, _, _ in PAIRS}
    assert len(PAIRS) >= 5, f"expected >=5 CRUD pairs, got {len(PAIRS)}"
    assert len(unique_servers) >= 5, (
        f"expected >=5 servers with same-bucket pairs, got {len(unique_servers)}"
    )
