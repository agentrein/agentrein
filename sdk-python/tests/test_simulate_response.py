from __future__ import annotations

from datetime import datetime

import pytest

from agentrein.simulate_response import SimulatedResponse, create_simulated_response


def test_dunder_guard() -> None:
    resp = create_simulated_response()
    with pytest.raises(AttributeError):
        _ = resp.__await__

    with pytest.raises(AttributeError):
        _ = resp.__iter__


def test_simulated_attribute() -> None:
    resp = create_simulated_response()
    assert resp.simulated is True


def test_to_dict_and_json() -> None:
    resp = create_simulated_response()
    assert callable(resp.to_dict)
    assert resp.to_dict() == {"simulated": True}

    assert callable(resp.json)
    assert resp.json() == {"simulated": True}


def test_id_attributes() -> None:
    resp = create_simulated_response()
    val_id = resp.id
    assert val_id.startswith("sim_id_")

    val_custom_id = resp.custom_id
    assert val_custom_id.startswith("sim_custom_id_")


def test_url_attributes() -> None:
    resp = create_simulated_response()
    assert resp.url == "https://sandbox.agentrein.com"
    assert resp.custom_url == "https://sandbox.agentrein.com"


def test_number_attribute() -> None:
    resp = create_simulated_response()
    assert resp.number == 0


def test_status_attribute() -> None:
    resp = create_simulated_response()
    assert resp.status == "simulated"


def test_created_attributes() -> None:
    resp = create_simulated_response()
    created = resp.created
    created_at = resp.created_at

    # Verify they parse as ISO timestamps
    dt_created = datetime.fromisoformat(created)
    dt_created_at = datetime.fromisoformat(created_at)

    # Verify they are timezone-aware (UTC)
    assert dt_created.tzinfo is not None
    assert dt_created_at.tzinfo is not None


def test_recursive_fallback() -> None:
    resp = create_simulated_response()
    nested = resp.some_random_attribute
    assert isinstance(nested, SimulatedResponse)

    # Verify we can chain deep nested accesses
    assert nested.another_random_attribute.nested_id.startswith("sim_nested_id_")
