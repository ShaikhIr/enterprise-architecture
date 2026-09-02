"""
Unit tests for master data domain entities.
Pure in-memory: no database, no I/O.
"""

from datetime import date

import pytest

from src.domain.entities.category_of_law import CategoryOfLaw
from src.domain.entities.country import Country
from src.domain.entities.legislation import Legislation
from src.domain.entities.rule import Rule
from src.domain.entities.state import State
from src.domain.entities.task_type import TaskType


class TestRequiredFields:
    """kw_only dataclasses must reject construction without mandatory fields."""

    def test_country_requires_code_and_name(self) -> None:
        with pytest.raises(TypeError):
            Country()  # type: ignore[call-arg]

    def test_state_requires_country(self) -> None:
        """A state cannot exist without the country that owns it."""
        with pytest.raises(TypeError):
            State(code="IN-MH", name="Maharashtra")  # type: ignore[call-arg]

    def test_legislation_requires_country_and_category(self) -> None:
        with pytest.raises(TypeError):
            Legislation(code="X", name="X")  # type: ignore[call-arg]

    def test_rule_requires_legislation_and_country(self) -> None:
        with pytest.raises(TypeError):
            Rule(code="X", name="X")  # type: ignore[call-arg]

    def test_task_type_requires_code_and_name(self) -> None:
        with pytest.raises(TypeError):
            TaskType()  # type: ignore[call-arg]


class TestAuditDefaults:
    """Every master inherits identity and audit defaults from BaseEntity."""

    def test_id_and_audit_fields_are_defaulted(self) -> None:
        country = Country(code="IN", name="India")

        # id defaults to the unsaved sentinel 0; the database assigns the real id.
        assert country.id == 0
        assert country.created_by == "system"
        assert country.modified_by == "system"
        assert country.created_date is not None

    def test_mark_modified_updates_actor_and_timestamp(self) -> None:
        country = Country(code="IN", name="India")
        before = country.modified_date

        country.mark_modified("alice")

        assert country.modified_by == "alice"
        assert country.modified_date >= before


class TestActivation:
    """is_active is the soft-retirement switch for all masters."""

    def test_defaults_to_active(self) -> None:
        assert Country(code="IN", name="India").is_active is True

    def test_deactivate_then_activate(self) -> None:
        task_type = TaskType(code="RETURN_FILING", name="Return Filing")

        task_type.deactivate()
        assert task_type.is_active is False

        task_type.activate()
        assert task_type.is_active is True


class TestJurisdictionSemantics:
    def test_legislation_without_state_is_central(self) -> None:
        """A country-level act with no state is central (federal)."""
        legislation = Legislation(
            code="IN-FACT-1948",
            name="The Factories Act, 1948",
            category_of_law_id=1,
            country_id=2,
            effective_date=date(1948, 4, 1),
        )

        assert legislation.is_central is True
        assert legislation.state_id is None

    def test_legislation_with_state_is_not_central(self) -> None:
        legislation = Legislation(
            code="MH-SHOPS-1948",
            name="Maharashtra Shops Act",
            category_of_law_id=1,
            country_id=2,
            state_id=3,
        )

        assert legislation.is_central is False

    def test_category_state_scoping(self) -> None:
        """A category is state specific only when a state is attached."""
        assert CategoryOfLaw(code="LABOUR", name="Labour Law").is_state_specific is False
        assert (
            CategoryOfLaw(
                code="LABOUR", name="Labour Law", state_id=3
            ).is_state_specific
            is True
        )
