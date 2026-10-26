"""What an AI agent (an MCP client, later in-product agents) may do, and the policy for it.

Every action an agent can take is listed here. Each organization sets a mode per action:
- never: the agent may not do it, not even propose it;
- approval: the agent proposes it and a person (an admin or analyst) approves or rejects it;
- allowed: the agent does it directly, with the same permission checks as an analyst.
Actions that reach outside the organization (emailing a supplier) can be at most "approval":
nothing leaves the organization without a person deciding.

Reading is not an action: read access for agents is set by the API key's scope.
"""

from typing import Any, Dict

MODES = ("never", "approval", "allowed")

ACTIONS: Dict[str, Dict[str, Any]] = {
    "incident.open": {"label": "Open a war-room incident", "default": "approval", "external": False},
    "incident.note": {"label": "Add a note to a war-room incident", "default": "approval", "external": False},
    "watchlist.add": {"label": "Add a term to the regulatory watchlist", "default": "approval", "external": False},
    "assessment.send": {"label": "Send a questionnaire to a supplier (emails someone outside the organization)",
                        "default": "never", "external": True},
}


def check_mode(action: str, mode: str) -> None:
    """Raises ValueError with a message if the mode is not allowed for the action."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown action {action!r}")
    if mode not in MODES:
        raise ValueError(f"The mode must be one of {', '.join(MODES)}")
    if ACTIONS[action]["external"] and mode == "allowed":
        raise ValueError("Actions that reach outside the organization always need a person's approval")


def effective(stored: Dict[str, str]) -> Dict[str, str]:
    """The mode of every action: the organization's setting, or the default."""
    return {name: stored.get(name, spec["default"]) for name, spec in ACTIONS.items()}
