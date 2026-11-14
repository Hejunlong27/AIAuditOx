"""Deterministic topological layering for procedure dependencies."""

from __future__ import annotations

from collections.abc import Mapping


class DagError(ValueError):
    """Dependency graph is missing a node or contains a cycle."""


def topological_layers(dependencies: Mapping[str, list[str]]) -> list[list[str]]:
    """Return deterministic dependency layers, with each layer sorted by id."""
    nodes = set(dependencies)
    for node, deps in dependencies.items():
        missing = [dep for dep in deps if dep not in nodes]
        if missing:
            raise DagError(f"程序 {node} 依赖不存在的程序：{', '.join(missing)}")

    indegree = {node: len(set(dependencies[node])) for node in nodes}
    outgoing = {node: set() for node in nodes}
    for node, deps in dependencies.items():
        for dep in set(deps):
            outgoing[dep].add(node)

    layers: list[list[str]] = []
    ready = sorted(node for node, count in indegree.items() if count == 0)
    processed = 0
    while ready:
        layer = ready
        layers.append(layer)
        processed += len(layer)
        next_ready: list[str] = []
        for node in layer:
            for child in sorted(outgoing[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_ready.append(child)
        ready = sorted(set(next_ready))

    if processed != len(nodes):
        cyclic = sorted(node for node, count in indegree.items() if count > 0)
        raise DagError(f"依赖图存在环，涉及：{', '.join(cyclic)}")
    return layers
