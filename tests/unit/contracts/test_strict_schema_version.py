from __future__ import annotations

import pytest
from contract_samples import CONTRACT_CASES, Deserializer, PayloadFactory


@pytest.mark.parametrize(("name", "deserialize", "payload_factory"), CONTRACT_CASES)
@pytest.mark.parametrize("invalid_version", [True, 1.0, "1"])
def test_schema_version_requires_exact_integer_one(
    name: str,
    deserialize: Deserializer,
    payload_factory: PayloadFactory,
    invalid_version: object,
) -> None:
    payload = payload_factory()
    payload["schema_version"] = invalid_version

    with pytest.raises(ValueError, match="schema_version"):
        deserialize(payload)
