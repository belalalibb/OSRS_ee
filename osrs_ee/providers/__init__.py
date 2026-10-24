"""Real AI providers (S07b-local). Advisory only: the Advisor validates every reply
against the AIProposal contract and never executes anything. Network code uses
stdlib ``urllib`` with an allowlisted base URL, bounded timeout and a ``ref:env:``
API key that becomes a Redactor canary. Tested only against a loopback fake server.
"""
from .openai_compat import OpenAICompatProvider, ProviderConfig, ProviderError

__all__ = ["OpenAICompatProvider", "ProviderConfig", "ProviderError"]
