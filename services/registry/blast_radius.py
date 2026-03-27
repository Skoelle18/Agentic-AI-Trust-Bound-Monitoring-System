from __future__ import annotations

from typing import Any

import networkx as nx
import yaml


def load_allowlist(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def compute_blast_radius(*, agent_id: str, tool_manifest: list[str], allowlist: dict[str, Any]) -> dict[str, Any]:
    """
    Build agent -> tool -> upstream_system graph.
    """
    g = nx.DiGraph()
    g.add_node(agent_id, type="agent", label=agent_id)

    tools_cfg = {t.get("name"): t for t in allowlist.get("tools", [])}
    systems_cfg = allowlist.get("systems", {}) or {}

    for tool in tool_manifest:
        tool_node = f"tool:{tool}"
        g.add_node(tool_node, type="tool", label=tool)
        g.add_edge(agent_id, tool_node, label="calls")

        upstream = (tools_cfg.get(tool) or {}).get("upstream_system")
        if upstream:
            sys_cfg = systems_cfg.get(upstream, {})
            sys_type = sys_cfg.get("type", "system")
            sys_label = sys_cfg.get("label", upstream)
            sys_node = f"{sys_type}:{upstream}"
            g.add_node(sys_node, type=sys_type, label=sys_label)
            g.add_edge(tool_node, sys_node, label="touches")

    nodes = [{"id": n, **g.nodes[n]} for n in g.nodes]
    edges = [{"source": u, "target": v, "label": g.edges[(u, v)].get("label", "")} for u, v in g.edges]
    return {"nodes": nodes, "edges": edges}

