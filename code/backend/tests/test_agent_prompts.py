"""Tests verifying that all Google ADK agent prompt instructions compile without KeyError."""
import re
from agents.agent import root_agent


def test_all_agent_instructions_compile_cleanly():
    """Verify that every agent in the root_agent hierarchy has valid instructions without KeyError."""
    visited = set()

    def check_agent(agent):
        name = getattr(agent, "name", agent.__class__.__name__)
        if name in visited:
            return
        visited.add(name)

        instruction = getattr(agent, "instruction", "")
        assert instruction is not None, f"Agent {name} has None instruction"
        
        # Check for unescaped {var} that are not known ADK state variables (e.g. project_id, outline)
        # Note: in ADK prompt templates, unescaped {word} where word is not a context variable raises KeyError
        suspicious_matches = re.findall(r"(?<!\{)\{([a-zA-Z0-9_]+)\}(?!})", instruction)
        allowed_vars = {"project_id", "outline", "section_title", "style"}
        for var in suspicious_matches:
            assert var in allowed_vars, (
                f"Agent '{name}' has suspicious unescaped template variable '{{{var}}}' "
                f"in instruction which could trigger ADK KeyError during runtime."
            )

        for sub in getattr(agent, "sub_agents", []):
            check_agent(sub)

    check_agent(root_agent)
