"""
SCIRM DAG-Based Multi-Agent Orchestrator
Replaces linear pipeline with a directed acyclic graph where agents
run in parallel when their dependencies are met.
"""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger()


class AgentNode:
    """A node in the agent DAG representing a single agent task."""

    def __init__(
        self,
        name: str,
        handler: Callable,
        depends_on: List[str] = None,
        optional: bool = False,
    ):
        self.name = name
        self.handler = handler
        self.depends_on = depends_on or []
        self.optional = optional  # If True, failure doesn't block downstream


class DAGExecutor:
    """
    Executes an agent DAG with maximum parallelism.
    Agents run as soon as all their dependencies complete.
    """

    def __init__(self):
        self.nodes: Dict[str, AgentNode] = {}
        self.results: Dict[str, Any] = {}
        self.errors: Dict[str, str] = {}
        self.timings: Dict[str, float] = {}

    def add_node(self, node: AgentNode) -> "DAGExecutor":
        self.nodes[node.name] = node
        return self

    def add(self, name: str, handler: Callable, depends_on: List[str] = None, optional: bool = False) -> "DAGExecutor":
        self.nodes[name] = AgentNode(name, handler, depends_on or [], optional)
        return self

    async def execute(self, initial_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute the DAG, running nodes in parallel where possible."""
        self.results = dict(initial_context or {})
        self.errors = {}
        self.timings = {}
        completed: Set[str] = set()
        pending = set(self.nodes.keys())

        logger.info("DAG execution started", nodes=list(pending))

        while pending:
            # Find nodes whose dependencies are all completed
            ready = [
                name for name in pending
                if all(dep in completed for dep in self.nodes[name].depends_on)
            ]

            if not ready:
                # Deadlock or unresolvable dependencies
                logger.error("DAG deadlock", pending=list(pending), completed=list(completed))
                break

            # Execute all ready nodes in parallel
            tasks = [self._run_node(name) for name in ready]
            await asyncio.gather(*tasks, return_exceptions=True)

            for name in ready:
                completed.add(name)
                pending.discard(name)

        logger.info(
            "DAG execution complete",
            completed=list(completed),
            errors=list(self.errors.keys()),
            total_time_ms=sum(self.timings.values()),
        )

        return {
            "results": self.results,
            "errors": self.errors,
            "timings": self.timings,
            "execution_order": list(completed),
        }

    async def _run_node(self, name: str) -> None:
        """Execute a single agent node."""
        node = self.nodes[name]
        start = time.time()

        try:
            logger.info("DAG node started", node=name, depends_on=node.depends_on)
            result = await node.handler(self.results)
            self.results[name] = result
            duration = (time.time() - start) * 1000
            self.timings[name] = round(duration, 1)
            logger.info("DAG node completed", node=name, duration_ms=round(duration, 1))

        except Exception as exc:
            duration = (time.time() - start) * 1000
            self.timings[name] = round(duration, 1)
            self.errors[name] = str(exc)

            if node.optional:
                logger.warning("DAG optional node failed", node=name, error=str(exc))
                self.results[name] = {}
            else:
                logger.error("DAG node failed", node=name, error=str(exc))
                self.results[name] = {"error": str(exc)}

    def get_execution_plan(self) -> List[List[str]]:
        """Preview the execution order as parallel batches."""
        completed: Set[str] = set()
        remaining = set(self.nodes.keys())
        batches = []

        while remaining:
            batch = [
                name for name in remaining
                if all(dep in completed for dep in self.nodes[name].depends_on)
            ]
            if not batch:
                break
            batches.append(batch)
            completed.update(batch)
            remaining -= set(batch)

        return batches


def create_assessment_dag() -> DAGExecutor:
    """
    Create the standard SCIRM risk assessment DAG.

    Execution graph:
        planner ──┐
                   ├──→ executor ──→ reviewer
        researcher ┘

    Planner and Researcher run in PARALLEL (no dependency between them).
    Executor waits for both. Reviewer waits for executor.
    """
    dag = DAGExecutor()
    # These handlers would be replaced with actual agent calls
    # when integrated into the coordinator
    return dag
