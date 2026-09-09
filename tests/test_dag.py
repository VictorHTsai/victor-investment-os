import pytest

from victor_investment_os.models import ComponentResult, FailureCode
from victor_investment_os.orchestrator.dag import CircularDependencyError, DAGExecutor, Node


def ok(name):
    return lambda upstream: ComponentResult.success(name, {"dependencies": sorted(upstream)})


def test_dependency_resolution_and_execution_order():
    nodes = {
        "a": Node("a", frozenset(), ok("a")),
        "b": Node("b", frozenset(), ok("b")),
        "c": Node("c", frozenset({"a", "b"}), ok("c")),
        "d": Node("d", frozenset({"c"}), ok("d")),
    }
    results, levels = DAGExecutor().execute(nodes)
    assert levels == [["a", "b"], ["c"], ["d"]]
    assert all(result.status == "SUCCESS" for result in results.values())


def test_circular_dependency_detection():
    nodes = {"a": Node("a", frozenset({"b"}), ok("a")),
             "b": Node("b", frozenset({"a"}), ok("b"))}
    with pytest.raises(CircularDependencyError):
        DAGExecutor().levels(nodes)


def test_failure_is_explicit_and_partial_node_can_run():
    nodes = {
        "a": Node("a", frozenset(), lambda _: ComponentResult.failed("a", FailureCode.ENGINE_FAILED, "boom")),
        "blocked": Node("blocked", frozenset({"a"}), ok("blocked")),
        "partial": Node("partial", frozenset({"a"}), ok("partial"), allow_partial=True),
    }
    results, _ = DAGExecutor().execute(nodes)
    assert results["blocked"].failure.code == "DEPENDENCY_FAILED"
    assert results["partial"].status == "SUCCESS"

