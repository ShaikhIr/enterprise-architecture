"""
ApprovalMatrixRepositoryImpl tests, against a real database session.

The repository persists a matrix as a whole aggregate (the matrix row plus its rules
and assignments), and also owns the `approval_tasks` table. The tests cover:

* aggregate create / read / update, including that `update` replaces both child
  collections wholesale and that `create` stamps the children with the real,
  database-assigned matrix id;
* listing with search / active / entity-type filters, pagination, `(priority, code)`
  ordering and a mirrored `count`; `list_active_for_entity_type`;
* code and case-insensitive name uniqueness (with `exclude_id`);
* the database cascade from a matrix to its children;
* approval tasks: create / get / update, ordering, the pending-for-user queue and
  bulk cancellation of an instance's open tasks;
* the entity <-> ORM mapping, including nullable columns (assignment `user_id` /
  `role_id`, task `matrix_id` / `action_taken` / `due_date` / `comments`).

Approval assignments and tasks have foreign keys to users, roles and workflow
instances, so tests build those through the real repositories. List and count
assertions are scoped by a unique `entity_type` so they do not depend on whatever else
is in the test database.
"""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.approval_matrix import (
    ApprovalAssignment,
    ApprovalMatrix,
    ApprovalRule,
    ApprovalTask,
)
from src.domain.entities.role import Role
from src.domain.entities.user import User
from src.domain.entities.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStatus,
)
from src.domain.enums.workflow_enums import (
    ApprovalTaskStatus,
    AssignmentType,
    RuleDataType,
    RuleOperator,
)
from src.infrastructure.database.models.approval_matrix_model import (
    ApprovalAssignmentModel,
    ApprovalRuleModel,
)
from src.infrastructure.database.repositories.approval_matrix_repository_impl import (
    ApprovalMatrixRepositoryImpl,
)
from src.infrastructure.database.repositories.role_repository_impl import (
    RoleRepositoryImpl,
)
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_definition_repository_impl import (
    WorkflowDefinitionRepositoryImpl,
)
from src.infrastructure.database.repositories.workflow_instance_repository_impl import (
    WorkflowInstanceRepositoryImpl,
)

_MISSING_ID = 999_999_999_999
_BASE_TIME = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)


def _token() -> str:
    return secrets.token_hex(5).upper()


def _matrix(**overrides: object) -> ApprovalMatrix:
    token = _token()
    defaults: dict[str, object] = {
        "code": f"AM{token}",
        "name": f"Matrix {token}",
        "entity_type": f"type_{token}",
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return ApprovalMatrix(**defaults)  # type: ignore[arg-type]


def _rule(**overrides: object) -> ApprovalRule:
    defaults: dict[str, object] = {"field": "amount", "value": "100"}
    defaults.update(overrides)
    return ApprovalRule(**defaults)  # type: ignore[arg-type]


async def _make_user(session: AsyncSession, **overrides: object) -> User:
    defaults: dict[str, object] = {
        "username": f"user-{_token()}",
        "password_hash": "x",
        "created_by": "t",
        "modified_by": "t",
    }
    defaults.update(overrides)
    return await UserRepositoryImpl(session).create(User(**defaults))  # type: ignore[arg-type]


async def _make_role(session: AsyncSession) -> Role:
    return await RoleRepositoryImpl(session).create(
        Role(code=f"ROLE{_token()}", name=f"Role {_token()}", created_by="t", modified_by="t")
    )


async def _make_instance(session: AsyncSession, initiator: User) -> WorkflowInstance:
    """Build a definition + status + instance, the parent every approval task needs."""
    definitions = WorkflowDefinitionRepositoryImpl(session)
    token = _token()
    definition = await definitions.create(
        WorkflowDefinition(
            code=f"WF{token}",
            name=f"Workflow {token}",
            entity_type=f"type_{token}",
            created_by="t",
            modified_by="t",
        )
    )
    status = await definitions.create_status(
        WorkflowStatus(
            workflow_definition_id=definition.id,
            code="START",
            name="Start",
            is_initial=True,
            created_by="t",
            modified_by="t",
        )
    )
    return await WorkflowInstanceRepositoryImpl(session).create(
        WorkflowInstance(
            workflow_definition_id=definition.id,
            entity_type=definition.entity_type,
            entity_id=1,
            current_status_id=status.id,
            initiated_by=initiator.id,
            created_by="t",
            modified_by="t",
        )
    )


def _task(instance_id: int, assignee_id: int, **overrides: object) -> ApprovalTask:
    defaults: dict[str, object] = {
        "instance_id": instance_id,
        "assignee_id": assignee_id,
        "created_by": "test",
        "modified_by": "test",
    }
    defaults.update(overrides)
    return ApprovalTask(**defaults)  # type: ignore[arg-type]


class TestCreateAndGetAggregate:
    async def test_create_round_trips_the_matrix_row(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(
            _matrix(priority=4, is_active=False, created_by="alice", modified_by="bob")
        )
        db_session.expire_all()  # force the read below to hit the row, not the identity map
        fetched = await repo.get_by_id(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.code == created.code
        assert fetched.name == created.name
        assert fetched.entity_type == created.entity_type
        assert fetched.priority == 4
        assert fetched.is_active is False
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_matrix_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(_matrix())
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.priority == 0
        assert fetched.is_active is True
        assert fetched.rules == []
        assert fetched.assignments == []

    async def test_create_persists_rules_with_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(
            _matrix(
                rules=[
                    _rule(
                        field="claim.amount",
                        operator=RuleOperator.GTE,
                        value="100000",
                        data_type=RuleDataType.NUMBER,
                        logical_group="high-value",
                    )
                ],
                modified_by="bob",
            )
        )
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        [rule] = fetched.rules
        assert rule.id > 0
        assert rule.matrix_id == created.id
        assert rule.field == "claim.amount"
        assert rule.operator is RuleOperator.GTE
        assert rule.value == "100000"
        assert rule.data_type is RuleDataType.NUMBER
        assert rule.logical_group == "high-value"
        # The repository stamps child audit columns from the matrix's modified_by.
        assert rule.created_by == "bob"
        assert rule.modified_by == "bob"

    async def test_rule_defaults_are_persisted(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(_matrix(rules=[_rule()]))
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        [rule] = fetched.rules
        assert rule.operator is RuleOperator.EQ
        assert rule.data_type is RuleDataType.STRING
        assert rule.logical_group == "default"

    @pytest.mark.parametrize("operator", list(RuleOperator))
    async def test_every_rule_operator_round_trips_as_its_enum(
        self, db_session: AsyncSession, operator: RuleOperator
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(_matrix(rules=[_rule(operator=operator)]))
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.rules[0].operator is operator

    @pytest.mark.parametrize("data_type", list(RuleDataType))
    async def test_every_rule_data_type_round_trips_as_its_enum(
        self, db_session: AsyncSession, data_type: RuleDataType
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        created = await repo.create(_matrix(rules=[_rule(data_type=data_type)]))
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.rules[0].data_type is data_type

    async def test_create_persists_a_role_assignment_with_null_user(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        role = await _make_role(db_session)

        created = await repo.create(
            _matrix(
                assignments=[
                    ApprovalAssignment(
                        assignment_type=AssignmentType.ROLE, role_id=role.id, level=2
                    )
                ]
            )
        )
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        [assignment] = fetched.assignments
        assert assignment.id > 0
        assert assignment.matrix_id == created.id
        assert assignment.assignment_type is AssignmentType.ROLE
        assert assignment.role_id == role.id
        assert assignment.user_id is None
        assert assignment.level == 2

    async def test_create_persists_a_user_assignment_with_null_role(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)

        created = await repo.create(
            _matrix(
                assignments=[
                    ApprovalAssignment(assignment_type=AssignmentType.USER, user_id=user.id)
                ]
            )
        )
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        [assignment] = fetched.assignments
        assert assignment.assignment_type is AssignmentType.USER
        assert assignment.user_id == user.id
        assert assignment.role_id is None
        assert assignment.level == 1  # entity default

    async def test_create_stamps_children_with_the_database_assigned_matrix_id(
        self, db_session: AsyncSession
    ) -> None:
        """The aggregate arrives with id 0; its children must not inherit that sentinel."""
        repo = ApprovalMatrixRepositoryImpl(db_session)
        role = await _make_role(db_session)

        created = await repo.create(
            _matrix(
                rules=[_rule(), _rule(field="region", value="EU")],
                assignments=[ApprovalAssignment(role_id=role.id)],
            )
        )

        assert created.id > 0
        assert {r.matrix_id for r in created.rules} == {created.id}
        assert {a.matrix_id for a in created.assignments} == {created.id}

    async def test_get_by_id_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        assert await repo.get_by_id(_MISSING_ID) is None

    async def test_get_by_code_returns_the_hydrated_aggregate(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix(rules=[_rule()]))

        fetched = await repo.get_by_code(created.code)

        assert fetched is not None
        assert fetched.id == created.id
        assert len(fetched.rules) == 1
        assert await repo.get_by_code(f"MISSING{_token()}") is None

    async def test_rules_are_ordered_by_logical_group_then_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(
            _matrix(
                rules=[
                    _rule(field="zeta", logical_group="b"),
                    _rule(field="beta", logical_group="a"),
                    _rule(field="alpha", logical_group="b"),
                    _rule(field="gamma", logical_group="a"),
                ]
            )
        )
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert [(r.logical_group, r.field) for r in fetched.rules] == [
            ("a", "beta"),
            ("a", "gamma"),
            ("b", "alpha"),
            ("b", "zeta"),
        ]

    async def test_assignments_are_ordered_by_level(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        roles = [await _make_role(db_session) for _ in range(3)]
        created = await repo.create(
            _matrix(
                assignments=[
                    ApprovalAssignment(role_id=roles[0].id, level=3),
                    ApprovalAssignment(role_id=roles[1].id, level=1),
                    ApprovalAssignment(role_id=roles[2].id, level=2),
                ]
            )
        )
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert [a.level for a in fetched.assignments] == [1, 2, 3]
        assert [a.role_id for a in fetched.assignments] == [
            roles[1].id,
            roles[2].id,
            roles[0].id,
        ]
        assert fetched.levels == [1, 2, 3]


class TestUpdateAggregate:
    async def test_update_persists_every_matrix_field(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix())
        token = _token()

        created.code = f"NEW{token}"
        created.name = f"Renamed {token}"
        created.entity_type = f"newtype_{token}"
        created.priority = 9
        created.is_active = False
        created.mark_modified("editor")
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert updated.code == f"NEW{token}"
        assert fetched is not None
        assert fetched.code == f"NEW{token}"
        assert fetched.name == f"Renamed {token}"
        assert fetched.entity_type == f"newtype_{token}"
        assert fetched.priority == 9
        assert fetched.is_active is False
        assert fetched.modified_by == "editor"

    async def test_update_replaces_rules_wholesale(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(
            _matrix(rules=[_rule(field="old_a", value="1"), _rule(field="old_b", value="2")])
        )

        created.rules = [_rule(field="new_only", value="9")]
        updated = await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert [r.field for r in updated.rules] == ["new_only"]
        assert fetched is not None
        assert [r.field for r in fetched.rules] == ["new_only"]
        assert fetched.rules[0].matrix_id == created.id

    async def test_update_replaces_assignments_wholesale(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        old_role = await _make_role(db_session)
        new_user = await _make_user(db_session)
        created = await repo.create(
            _matrix(assignments=[ApprovalAssignment(role_id=old_role.id, level=1)])
        )

        created.assignments = [
            ApprovalAssignment(assignment_type=AssignmentType.USER, user_id=new_user.id, level=2)
        ]
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        [assignment] = fetched.assignments
        assert assignment.assignment_type is AssignmentType.USER
        assert assignment.user_id == new_user.id
        assert assignment.role_id is None
        assert assignment.level == 2

    async def test_update_with_no_children_clears_existing_ones(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        role = await _make_role(db_session)
        created = await repo.create(
            _matrix(rules=[_rule()], assignments=[ApprovalAssignment(role_id=role.id)])
        )

        created.rules = []
        created.assignments = []
        await repo.update(created)
        db_session.expire_all()
        fetched = await repo.get_by_id(created.id)

        assert fetched is not None
        assert fetched.rules == []
        assert fetched.assignments == []

    async def test_update_does_not_touch_other_matrices_children(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        edited = await repo.create(_matrix(rules=[_rule(field="mine")]))
        bystander = await repo.create(_matrix(rules=[_rule(field="theirs")]))

        edited.rules = []
        await repo.update(edited)
        db_session.expire_all()
        fetched = await repo.get_by_id(bystander.id)

        assert fetched is not None
        assert [r.field for r in fetched.rules] == ["theirs"]

    async def test_update_of_a_missing_matrix_raises(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        with pytest.raises(ValueError, match="not found"):
            await repo.update(_matrix(id=_MISSING_ID))


class TestDelete:
    async def test_delete_removes_the_matrix(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix())

        await repo.delete(created.id)

        assert await repo.get_by_id(created.id) is None

    async def test_delete_of_a_missing_matrix_is_silent(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        await repo.delete(_MISSING_ID)  # must not raise

    async def test_delete_cascades_to_rules_and_assignments(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        role = await _make_role(db_session)
        created = await repo.create(
            _matrix(rules=[_rule()], assignments=[ApprovalAssignment(role_id=role.id)])
        )

        await repo.delete(created.id)

        rules = await db_session.execute(
            select(ApprovalRuleModel.id).where(ApprovalRuleModel.matrix_id == created.id)
        )
        assignments = await db_session.execute(
            select(ApprovalAssignmentModel.id).where(
                ApprovalAssignmentModel.matrix_id == created.id
            )
        )
        assert rules.scalars().all() == []
        assert assignments.scalars().all() == []


class TestExistsByCodeAndName:
    async def test_exists_by_code_with_exclude_id(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix())
        other = await repo.create(_matrix())

        assert await repo.exists_by_code(created.code) is True
        assert await repo.exists_by_code(f"MISSING{_token()}") is False
        assert await repo.exists_by_code(created.code, exclude_id=created.id) is False
        assert await repo.exists_by_code(created.code, exclude_id=other.id) is True

    async def test_exists_by_name_is_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix(name=f"Mixed Case {_token()}"))

        assert await repo.exists_by_name(created.name) is True
        assert await repo.exists_by_name(created.name.upper()) is True
        assert await repo.exists_by_name(created.name.lower()) is True
        assert await repo.exists_by_name(f"No such matrix {_token()}") is False

    async def test_exists_by_name_with_exclude_id(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        created = await repo.create(_matrix())
        other = await repo.create(_matrix())

        assert await repo.exists_by_name(created.name, exclude_id=created.id) is False
        assert await repo.exists_by_name(created.name, exclude_id=other.id) is True


class TestListAndCount:
    async def test_list_all_is_ordered_by_priority_then_code(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        # Created out of order. Codes differ only in the last character, so the expected
        # order does not depend on the database collation.
        for suffix, priority in (("B", 2), ("C", 1), ("A", 2), ("D", 0)):
            await repo.create(
                _matrix(code=f"AM{token}{suffix}", entity_type=entity_type, priority=priority)
            )

        rows = await repo.list_all(entity_type=entity_type)

        assert [r.code for r in rows] == [
            f"AM{token}D",
            f"AM{token}C",
            f"AM{token}A",
            f"AM{token}B",
        ]

    async def test_pagination_skips_and_limits_and_count_ignores_it(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        for suffix in "ABCDE":
            await repo.create(_matrix(code=f"AM{token}{suffix}", entity_type=entity_type))

        page = await repo.list_all(skip=1, limit=2, entity_type=entity_type)
        total = await repo.count(entity_type=entity_type)

        assert [r.code for r in page] == [f"AM{token}B", f"AM{token}C"]
        assert total == 5

    async def test_list_all_hydrates_each_matrixs_own_children(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        role = await _make_role(db_session)
        await repo.create(
            _matrix(
                code=f"AM{token}A",
                entity_type=entity_type,
                rules=[_rule(field="a1"), _rule(field="a2")],
                assignments=[ApprovalAssignment(role_id=role.id)],
            )
        )
        await repo.create(
            _matrix(code=f"AM{token}B", entity_type=entity_type, rules=[_rule(field="b1")])
        )
        await repo.create(_matrix(code=f"AM{token}C", entity_type=entity_type))
        db_session.expire_all()

        rows = {r.code: r for r in await repo.list_all(entity_type=entity_type)}

        assert [r.field for r in rows[f"AM{token}A"].rules] == ["a1", "a2"]
        assert len(rows[f"AM{token}A"].assignments) == 1
        assert [r.field for r in rows[f"AM{token}B"].rules] == ["b1"]
        assert rows[f"AM{token}B"].assignments == []
        assert rows[f"AM{token}C"].rules == []
        assert rows[f"AM{token}C"].assignments == []

    async def test_entity_type_filter_is_an_exact_match(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        entity_type = f"type_{_token()}"
        mine = await repo.create(_matrix(entity_type=entity_type))
        await repo.create(_matrix(entity_type=f"{entity_type}_other"))

        rows = await repo.list_all(entity_type=entity_type)

        assert [r.id for r in rows] == [mine.id]
        assert await repo.count(entity_type=entity_type) == 1

    async def test_is_active_filter(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        entity_type = f"type_{_token()}"
        active = await repo.create(_matrix(entity_type=entity_type))
        inactive = await repo.create(_matrix(entity_type=entity_type, is_active=False))

        active_rows = await repo.list_all(entity_type=entity_type, is_active=True)
        inactive_rows = await repo.list_all(entity_type=entity_type, is_active=False)

        assert [r.id for r in active_rows] == [active.id]
        assert [r.id for r in inactive_rows] == [inactive.id]
        assert await repo.count(entity_type=entity_type, is_active=True) == 1
        assert await repo.count(entity_type=entity_type, is_active=False) == 1
        assert await repo.count(entity_type=entity_type) == 2

    async def test_search_matches_code_name_and_entity_type_case_insensitively(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        needle = _token()
        by_code = await repo.create(_matrix(code=f"CODE{needle}X"))
        by_name = await repo.create(_matrix(name=f"Named {needle.lower()} matrix"))
        by_type = await repo.create(_matrix(entity_type=f"kind_{needle}"))
        await repo.create(_matrix())  # matches nothing

        rows = await repo.list_all(search=needle)

        assert {r.id for r in rows} == {by_code.id, by_name.id, by_type.id}
        assert await repo.count(search=needle) == 3

    async def test_filters_combine_with_and_and_count_mirrors_them(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        needle = _token()
        entity_type = f"type_{needle}"
        match = await repo.create(_matrix(code=f"A{needle}", entity_type=entity_type))
        await repo.create(
            _matrix(code=f"B{needle}", entity_type=entity_type, is_active=False)
        )
        await repo.create(_matrix(code=f"C{needle}", entity_type=f"other_{needle}"))

        rows = await repo.list_all(search=needle, is_active=True, entity_type=entity_type)
        total = await repo.count(search=needle, is_active=True, entity_type=entity_type)

        assert [r.id for r in rows] == [match.id]
        assert total == 1

    async def test_no_match_gives_an_empty_list_and_a_zero_count(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        assert await repo.list_all(search=f"nothing-{_token()}") == []
        assert await repo.count(search=f"nothing-{_token()}") == 0


class TestListActiveForEntityType:
    async def test_returns_only_active_matrices_of_that_type_in_priority_order(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        token = _token()
        entity_type = f"type_{token}"
        await repo.create(
            _matrix(code=f"AM{token}B", entity_type=entity_type, priority=2)
        )
        await repo.create(
            _matrix(code=f"AM{token}A", entity_type=entity_type, priority=2)
        )
        await repo.create(
            _matrix(code=f"AM{token}C", entity_type=entity_type, priority=1)
        )
        await repo.create(
            _matrix(code=f"AM{token}D", entity_type=entity_type, is_active=False)
        )
        await repo.create(_matrix(entity_type=f"other_{token}"))

        rows = await repo.list_active_for_entity_type(entity_type)

        assert [r.code for r in rows] == [f"AM{token}C", f"AM{token}A", f"AM{token}B"]

    async def test_hydrates_rules_and_assignments(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        entity_type = f"type_{_token()}"
        role = await _make_role(db_session)
        await repo.create(
            _matrix(
                entity_type=entity_type,
                rules=[_rule(field="amount")],
                assignments=[ApprovalAssignment(role_id=role.id)],
            )
        )
        db_session.expire_all()

        [row] = await repo.list_active_for_entity_type(entity_type)

        assert [r.field for r in row.rules] == ["amount"]
        assert [a.role_id for a in row.assignments] == [role.id]

    async def test_unknown_entity_type_returns_an_empty_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        assert await repo.list_active_for_entity_type(f"never_{_token()}") == []


class TestTaskCreateAndGet:
    async def test_create_task_round_trips_every_field(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        matrix = await repo.create(_matrix())
        due = _BASE_TIME + timedelta(days=2)

        created = await repo.create_task(
            _task(
                instance.id,
                user.id,
                matrix_id=matrix.id,
                level=3,
                status=ApprovalTaskStatus.COMPLETED,
                action_taken="APPROVE",
                due_date=due,
                comments="Fine by me",
                created_by="alice",
                modified_by="bob",
            )
        )
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert created.id > 0
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.instance_id == instance.id
        assert fetched.matrix_id == matrix.id
        assert fetched.assignee_id == user.id
        assert fetched.level == 3
        assert fetched.status is ApprovalTaskStatus.COMPLETED
        assert fetched.action_taken == "APPROVE"
        assert fetched.due_date == due
        assert fetched.comments == "Fine by me"
        assert fetched.created_by == "alice"
        assert fetched.modified_by == "bob"
        assert fetched.created_date is not None
        assert fetched.modified_date is not None

    async def test_nullable_columns_and_defaults_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)

        created = await repo.create_task(_task(instance.id, user.id))
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert fetched is not None
        assert fetched.matrix_id is None
        assert fetched.action_taken is None
        assert fetched.due_date is None
        assert fetched.comments is None
        assert fetched.level == 1
        assert fetched.status is ApprovalTaskStatus.PENDING
        assert fetched.is_open is True

    @pytest.mark.parametrize("status", list(ApprovalTaskStatus))
    async def test_every_task_status_round_trips_as_its_enum(
        self, db_session: AsyncSession, status: ApprovalTaskStatus
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)

        created = await repo.create_task(_task(instance.id, user.id, status=status))
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert fetched is not None
        assert fetched.status is status

    async def test_get_task_returns_none_for_a_missing_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)

        assert await repo.get_task(_MISSING_ID) is None

    async def test_deleting_the_matrix_nulls_the_tasks_matrix_reference(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        matrix = await repo.create(_matrix())
        task = await repo.create_task(_task(instance.id, user.id, matrix_id=matrix.id))

        await repo.delete(matrix.id)
        db_session.expire_all()  # the FK's SET NULL happened in the database, not the session
        fetched = await repo.get_task(task.id)

        assert fetched is not None
        assert fetched.matrix_id is None


class TestUpdateTask:
    async def test_update_task_persists_the_mutable_fields(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        created = await repo.create_task(_task(instance.id, user.id))
        due = _BASE_TIME + timedelta(days=5)

        created.level = 2
        created.status = ApprovalTaskStatus.COMPLETED
        created.action_taken = "REJECT"
        created.due_date = due
        created.comments = "Not enough detail"
        created.mark_modified("reviewer")
        updated = await repo.update_task(created)
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert updated.status is ApprovalTaskStatus.COMPLETED
        assert fetched is not None
        assert fetched.level == 2
        assert fetched.status is ApprovalTaskStatus.COMPLETED
        assert fetched.action_taken == "REJECT"
        assert fetched.due_date == due
        assert fetched.comments == "Not enough detail"
        assert fetched.modified_by == "reviewer"
        assert fetched.is_open is False

    async def test_update_task_can_clear_nullable_columns(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        created = await repo.create_task(
            _task(
                instance.id,
                user.id,
                action_taken="APPROVE",
                due_date=_BASE_TIME,
                comments="note",
            )
        )

        created.action_taken = None
        created.due_date = None
        created.comments = None
        await repo.update_task(created)
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert fetched is not None
        assert fetched.action_taken is None
        assert fetched.due_date is None
        assert fetched.comments is None

    async def test_update_task_does_not_change_instance_assignee_or_matrix(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other_user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        other_instance = await _make_instance(db_session, user)
        matrix = await repo.create(_matrix())
        created = await repo.create_task(_task(instance.id, user.id, matrix_id=matrix.id))

        created.instance_id = other_instance.id
        created.assignee_id = other_user.id
        created.matrix_id = None
        await repo.update_task(created)
        db_session.expire_all()
        fetched = await repo.get_task(created.id)

        assert fetched is not None
        assert fetched.instance_id == instance.id
        assert fetched.assignee_id == user.id
        assert fetched.matrix_id == matrix.id

    async def test_update_task_of_a_missing_task_raises(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)

        with pytest.raises(ValueError, match="not found"):
            await repo.update_task(_task(instance.id, user.id, id=_MISSING_ID))


class TestListTasksForInstance:
    async def test_is_ordered_by_level(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        for level in (3, 1, 2):
            await repo.create_task(_task(instance.id, user.id, level=level))

        rows = await repo.list_tasks_for_instance(instance.id)

        assert [r.level for r in rows] == [1, 2, 3]

    async def test_is_scoped_to_the_instance(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        other_instance = await _make_instance(db_session, user)
        mine = await repo.create_task(_task(instance.id, user.id))
        await repo.create_task(_task(other_instance.id, user.id))

        rows = await repo.list_tasks_for_instance(instance.id)

        assert [r.id for r in rows] == [mine.id]

    async def test_includes_tasks_of_every_status(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        for level, status in enumerate(ApprovalTaskStatus, start=1):
            await repo.create_task(_task(instance.id, user.id, level=level, status=status))

        rows = await repo.list_tasks_for_instance(instance.id)

        assert {r.status for r in rows} == set(ApprovalTaskStatus)

    async def test_returns_an_empty_list_for_an_instance_with_no_tasks(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)

        assert await repo.list_tasks_for_instance(instance.id) == []


class TestListPendingTasksForUser:
    async def test_returns_only_pending_tasks_of_that_assignee(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other_user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        pending = await repo.create_task(_task(instance.id, user.id, level=1))
        await repo.create_task(
            _task(instance.id, user.id, level=2, status=ApprovalTaskStatus.COMPLETED)
        )
        await repo.create_task(
            _task(instance.id, user.id, level=3, status=ApprovalTaskStatus.CANCELLED)
        )
        await repo.create_task(
            _task(instance.id, user.id, level=4, status=ApprovalTaskStatus.ESCALATED)
        )
        await repo.create_task(_task(instance.id, other_user.id, level=1))

        rows = await repo.list_pending_tasks_for_user(user.id)

        assert [r.id for r in rows] == [pending.id]

    async def test_is_ordered_by_due_date_with_undated_tasks_last(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        # Created out of due-date order; the undated one is created first so a plain
        # insertion order, or NULLs sorting first, would both fail this test.
        undated = await repo.create_task(_task(instance.id, user.id, level=1))
        later = await repo.create_task(
            _task(instance.id, user.id, level=2, due_date=_BASE_TIME + timedelta(days=5))
        )
        sooner = await repo.create_task(
            _task(instance.id, user.id, level=3, due_date=_BASE_TIME + timedelta(days=1))
        )

        rows = await repo.list_pending_tasks_for_user(user.id)

        assert [r.id for r in rows] == [sooner.id, later.id, undated.id]

    async def test_spans_instances(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        first = await _make_instance(db_session, user)
        second = await _make_instance(db_session, user)
        await repo.create_task(_task(first.id, user.id))
        await repo.create_task(_task(second.id, user.id))

        rows = await repo.list_pending_tasks_for_user(user.id)

        assert {r.instance_id for r in rows} == {first.id, second.id}

    async def test_returns_an_empty_list_for_a_user_with_nothing_pending(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)

        assert await repo.list_pending_tasks_for_user(user.id) == []


class TestCancelOpenTasksForInstance:
    async def test_cancels_pending_tasks_and_reports_the_count(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        other_user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        first = await repo.create_task(_task(instance.id, user.id, level=1))
        second = await repo.create_task(_task(instance.id, other_user.id, level=1))

        cancelled = await repo.cancel_open_tasks_for_instance(instance.id)
        db_session.expire_all()

        assert cancelled == 2
        for task_id in (first.id, second.id):
            fetched = await repo.get_task(task_id)
            assert fetched is not None
            assert fetched.status is ApprovalTaskStatus.CANCELLED
            assert fetched.is_open is False
        assert await repo.list_pending_tasks_for_user(user.id) == []

    async def test_leaves_already_settled_tasks_untouched(
        self, db_session: AsyncSession
    ) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        await repo.create_task(_task(instance.id, user.id, level=1))
        completed = await repo.create_task(
            _task(instance.id, user.id, level=2, status=ApprovalTaskStatus.COMPLETED)
        )
        escalated = await repo.create_task(
            _task(instance.id, user.id, level=3, status=ApprovalTaskStatus.ESCALATED)
        )

        cancelled = await repo.cancel_open_tasks_for_instance(instance.id)
        db_session.expire_all()
        completed_after = await repo.get_task(completed.id)
        escalated_after = await repo.get_task(escalated.id)

        assert cancelled == 1
        assert completed_after is not None
        assert completed_after.status is ApprovalTaskStatus.COMPLETED
        assert escalated_after is not None
        assert escalated_after.status is ApprovalTaskStatus.ESCALATED

    async def test_only_affects_the_given_instance(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)
        other_instance = await _make_instance(db_session, user)
        await repo.create_task(_task(instance.id, user.id))
        untouched = await repo.create_task(_task(other_instance.id, user.id))

        await repo.cancel_open_tasks_for_instance(instance.id)
        db_session.expire_all()
        fetched = await repo.get_task(untouched.id)

        assert fetched is not None
        assert fetched.status is ApprovalTaskStatus.PENDING

    async def test_returns_zero_when_nothing_is_open(self, db_session: AsyncSession) -> None:
        repo = ApprovalMatrixRepositoryImpl(db_session)
        user = await _make_user(db_session)
        instance = await _make_instance(db_session, user)

        assert await repo.cancel_open_tasks_for_instance(instance.id) == 0
