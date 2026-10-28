"""OSRS_ee pure contracts (S01). Offline only: no network, no game client,
no storage, no AI, no Telegram. Schema validity never proves lease ownership,
identity, or freshness; those are evaluated separately by `osrs_ee.guards`."""
__all__ = ["contracts", "canonical", "guards"]
