from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from ..models import ComponentResult, FailureCode


class CircularDependencyError(ValueError):
    pass


@dataclass(frozen=True)
class Node:
    name: str
    dependencies: frozenset[str]
    execute: Callable[[dict[str, ComponentResult]], ComponentResult]
    allow_partial: bool = False


class DAGExecutor:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def levels(self, nodes: dict[str, Node]) -> list[list[str]]:
        for node in nodes.values():
            unknown = node.dependencies - nodes.keys()
            if unknown:
                raise ValueError(f"{node.name} has unknown dependencies: {sorted(unknown)}")
        remaining = set(nodes)
        resolved: set[str] = set()
        levels: list[list[str]] = []
        while remaining:
            ready = sorted(name for name in remaining if nodes[name].dependencies <= resolved)
            if not ready:
                raise CircularDependencyError(f"Circular dependency among: {sorted(remaining)}")
            levels.append(ready)
            resolved.update(ready)
            remaining.difference_update(ready)
        return levels

    def execute(self, nodes: dict[str, Node]) -> tuple[dict[str, ComponentResult], list[list[str]]]:
        execution_levels = self.levels(nodes)
        results: dict[str, ComponentResult] = {}
        for level in execution_levels:
            runnable: list[Node] = []
            for name in level:
                node = nodes[name]
                failed_dependencies = [d for d in node.dependencies if results[d].status != "SUCCESS"]
                if failed_dependencies and not node.allow_partial:
                    results[name] = ComponentResult.failed(
                        name, FailureCode.DEPENDENCY_FAILED,
                        f"Failed dependencies: {', '.join(sorted(failed_dependencies))}")
                else:
                    runnable.append(node)
            with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(runnable)))) as pool:
                futures = {pool.submit(node.execute, {d: results[d] for d in node.dependencies}): node.name
                           for node in runnable}
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        results[name] = future.result()
                    except Exception as exc:
                        results[name] = ComponentResult.failed(name, FailureCode.ENGINE_FAILED, str(exc))
        return results, execution_levels

