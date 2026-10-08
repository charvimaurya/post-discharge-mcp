"""
Agent model selection.

MODEL_MODE=test
    → Claude Haiku 4.5

MODEL_MODE=final
    → Claude Sonnet 5
"""

from app import config


def get_agent_model_id() -> str:
    """
    Return the Bedrock model/inference profile used
    by the conversational agent.
    """

    if config.MODEL_MODE == "final":
        return config.FINAL_AGENT_MODEL_ID

    # During development we deliberately use the
    # cheaper/faster test model.
    return config.TEST_MODEL_ID