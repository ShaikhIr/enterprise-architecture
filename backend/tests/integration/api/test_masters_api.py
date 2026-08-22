"""
Integration tests for the master data API.

These run against a real Postgres test database inside a transaction that is
rolled back after each test, and authenticate with a real JWT against real
seeded RBAC rows — so permission enforcement is genuinely exercised, not stubbed.
"""

from typing import Any

from httpx import AsyncClient

COUNTRIES = "/api/v1/masters/countries"
STATES = "/api/v1/masters/states"
CATEGORIES = "/api/v1/masters/categories-of-law"
LEGISLATIONS = "/api/v1/masters/legislations"
RULES = "/api/v1/masters/rules"
TASK_TYPES = "/api/v1/masters/task-types"


async def _create_country(
    client: AsyncClient, code: str = "zz", name: str = "Testland"
) -> dict[str, Any]:
    response = await client.post(COUNTRIES, json={"code": code, "name": name})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _create_state(
    client: AsyncClient,
    country_id: str,
    code: str = "zz-ts",
    name: str = "Test State",
) -> dict[str, Any]:
    response = await client.post(
        STATES, json={"code": code, "name": name, "country_id": country_id}
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def _create_category(
    client: AsyncClient, state_id: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": "labour", "name": "Labour Law"}
    if state_id:
        payload["state_id"] = state_id
    response = await client.post(CATEGORIES, json=payload)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


class TestAuthorization:
    """Every master endpoint sits behind an API permission."""

    async def test_anonymous_request_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(COUNTRIES)
        assert response.status_code in (401, 403), response.text

    async def test_authenticated_admin_is_allowed(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(COUNTRIES)
        assert response.status_code == 200, response.text


class TestCountryCrud:
    async def test_create_returns_201_and_normalises_code(self, admin_client: AsyncClient) -> None:
        """Lowercase input is upper-cased by the schema validator."""
        country = await _create_country(admin_client, code="zz", name="Testland")

        assert country["code"] == "ZZ"
        assert country["name"] == "Testland"
        assert country["is_active"] is True
        assert country["created_by"] == "admin-test"

    async def test_list_includes_created_country(self, admin_client: AsyncClient) -> None:
        await _create_country(admin_client)

        response = await admin_client.get(COUNTRIES)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert any(c["code"] == "ZZ" for c in body["countries"])

    async def test_get_by_id(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)

        response = await admin_client.get(f"{COUNTRIES}/{country['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == country["id"]

    async def test_patch_updates_only_supplied_fields(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)

        response = await admin_client.patch(
            f"{COUNTRIES}/{country['id']}", json={"name": "Testlandia"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "Testlandia"
        assert body["code"] == "ZZ"  # untouched
        assert body["modified_by"] == "admin-test"

    async def test_delete_returns_204(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)

        response = await admin_client.delete(f"{COUNTRIES}/{country['id']}")
        assert response.status_code == 204

        follow_up = await admin_client.get(f"{COUNTRIES}/{country['id']}")
        assert follow_up.status_code == 404

    async def test_duplicate_code_returns_409(self, admin_client: AsyncClient) -> None:
        await _create_country(admin_client, code="zz", name="Testland")

        response = await admin_client.post(
            COUNTRIES, json={"code": "ZZ", "name": "Different Name"}
        )

        assert response.status_code == 409, response.text
        assert "already exists" in response.json()["message"]

    async def test_unknown_id_returns_404(self, admin_client: AsyncClient) -> None:
        response = await admin_client.get(
            f"{COUNTRIES}/00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404

    async def test_missing_required_field_returns_422(self, admin_client: AsyncClient) -> None:
        response = await admin_client.post(COUNTRIES, json={"code": "ZZ"})
        assert response.status_code == 422


class TestJurisdictionIntegrity:
    """The hierarchy must stay internally consistent."""

    async def test_state_requires_existing_country(self, admin_client: AsyncClient) -> None:
        response = await admin_client.post(
            STATES,
            json={
                "code": "ZZ-XX",
                "name": "Nowhere",
                "country_id": "00000000-0000-0000-0000-000000000000",
            },
        )

        assert response.status_code == 404, response.text
        assert "Country" in response.json()["message"]

    async def test_legislation_rejects_state_from_another_country(
        self, admin_client: AsyncClient
    ) -> None:
        """A state must belong to the legislation's country."""
        country = await _create_country(admin_client, code="zz", name="Testland")
        other = await _create_country(admin_client, code="zy", name="Otherland")
        state = await _create_state(admin_client, country["id"])
        category = await _create_category(admin_client, state["id"])

        response = await admin_client.post(
            LEGISLATIONS,
            json={
                "code": "zy-bad",
                "name": "Mismatched Act",
                "category_of_law_id": category["id"],
                "country_id": other["id"],
                "state_id": state["id"],
            },
        )

        assert response.status_code == 409, response.text
        assert "does not belong" in response.json()["message"]

    async def test_delete_blocked_while_state_references_country(
        self, admin_client: AsyncClient
    ) -> None:
        country = await _create_country(admin_client)
        await _create_state(admin_client, country["id"])

        response = await admin_client.delete(f"{COUNTRIES}/{country['id']}")

        assert response.status_code == 409, response.text
        assert "Deactivate it instead" in response.json()["message"]


class TestFullHierarchy:
    async def test_create_down_to_rule_and_filter(self, admin_client: AsyncClient) -> None:
        """Country -> state -> category -> legislation -> rule, then filter by parent."""
        country = await _create_country(admin_client)
        state = await _create_state(admin_client, country["id"])
        category = await _create_category(admin_client, state["id"])

        legislation_response = await admin_client.post(
            LEGISLATIONS,
            json={
                "code": "zz-fact-1948",
                "name": "The Test Factories Act, 1948",
                "category_of_law_id": category["id"],
                "country_id": country["id"],
                "state_id": state["id"],
                "legislation_number": "Act No. 1 of 1948",
                "effective_date": "1948-04-01",
            },
        )
        assert legislation_response.status_code == 201, legislation_response.text
        legislation = legislation_response.json()
        assert legislation["effective_date"] == "1948-04-01"

        rule_response = await admin_client.post(
            RULES,
            json={
                "code": "zz-fact-1948-r5",
                "name": "Maintenance of health register",
                "legislation_id": legislation["id"],
                "country_id": country["id"],
                "state_id": state["id"],
                "rule_number": "Rule 5(2)",
            },
        )
        assert rule_response.status_code == 201, rule_response.text

        # Filters narrow by parent
        states = await admin_client.get(STATES, params={"country_id": country["id"]})
        assert states.json()["total"] == 1

        rules = await admin_client.get(RULES, params={"legislation_id": legislation["id"]})
        assert rules.json()["total"] == 1

        # Search matches the rule number
        found = await admin_client.get(RULES, params={"search": "Rule 5"})
        assert found.json()["total"] == 1

    async def test_central_legislation_needs_no_state(self, admin_client: AsyncClient) -> None:
        """A federal act is valid with a country but no state."""
        country = await _create_country(admin_client)
        category = await _create_category(admin_client)

        response = await admin_client.post(
            LEGISLATIONS,
            json={
                "code": "zz-central",
                "name": "A Central Act",
                "category_of_law_id": category["id"],
                "country_id": country["id"],
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["state_id"] is None


class TestTaskTypes:
    async def test_code_is_normalised_to_upper_snake(self, admin_client: AsyncClient) -> None:
        response = await admin_client.post(
            TASK_TYPES, json={"code": "return filing", "name": "Return Filing"}
        )

        assert response.status_code == 201, response.text
        assert response.json()["code"] == "RETURN_FILING"

    async def test_is_active_filter(self, admin_client: AsyncClient) -> None:
        created = await admin_client.post(
            TASK_TYPES, json={"code": "audit", "name": "Audit"}
        )
        task_type_id = created.json()["id"]
        await admin_client.patch(f"{TASK_TYPES}/{task_type_id}", json={"is_active": False})

        active = await admin_client.get(TASK_TYPES, params={"is_active": True})
        inactive = await admin_client.get(TASK_TYPES, params={"is_active": False})

        assert all(t["is_active"] for t in active.json()["task_types"])
        assert any(t["id"] == task_type_id for t in inactive.json()["task_types"])


class TestUpdateAndDelete:
    """PATCH and DELETE across the rest of the hierarchy."""

    async def test_patch_state_moves_it_to_another_country(self, admin_client: AsyncClient) -> None:
        origin = await _create_country(admin_client, code="zz", name="Testland")
        destination = await _create_country(admin_client, code="zy", name="Otherland")
        state = await _create_state(admin_client, origin["id"])

        response = await admin_client.patch(
            f"{STATES}/{state['id']}", json={"country_id": destination["id"]}
        )

        assert response.status_code == 200, response.text
        assert response.json()["country_id"] == destination["id"]

    async def test_patch_state_rejects_duplicate_code(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)
        await _create_state(admin_client, country["id"], code="zz-aa", name="Alpha")
        second = await _create_state(
            admin_client, country["id"], code="zz-bb", name="Beta"
        )

        response = await admin_client.patch(
            f"{STATES}/{second['id']}", json={"code": "zz-aa"}
        )

        assert response.status_code == 409, response.text

    async def test_patch_state_to_unknown_country_returns_404(
        self, admin_client: AsyncClient
    ) -> None:
        country = await _create_country(admin_client)
        state = await _create_state(admin_client, country["id"])

        response = await admin_client.patch(
            f"{STATES}/{state['id']}",
            json={"country_id": "00000000-0000-0000-0000-000000000000"},
        )

        assert response.status_code == 404, response.text

    async def test_delete_leaf_state_succeeds(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)
        state = await _create_state(admin_client, country["id"])

        response = await admin_client.delete(f"{STATES}/{state['id']}")

        assert response.status_code == 204
        assert (await admin_client.get(f"{STATES}/{state['id']}")).status_code == 404

    async def test_patch_and_delete_category(self, admin_client: AsyncClient) -> None:
        category = await _create_category(admin_client)

        patched = await admin_client.patch(
            f"{CATEGORIES}/{category['id']}",
            json={"description": "Employment and industrial relations"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["description"] == "Employment and industrial relations"
        assert patched.json()["name"] == "Labour Law"

        deleted = await admin_client.delete(f"{CATEGORIES}/{category['id']}")
        assert deleted.status_code == 204

    async def test_category_delete_blocked_while_legislation_exists(
        self, admin_client: AsyncClient
    ) -> None:
        country = await _create_country(admin_client)
        category = await _create_category(admin_client)
        await admin_client.post(
            LEGISLATIONS,
            json={
                "code": "zz-act",
                "name": "An Act",
                "category_of_law_id": category["id"],
                "country_id": country["id"],
            },
        )

        response = await admin_client.delete(f"{CATEGORIES}/{category['id']}")

        assert response.status_code == 409, response.text
        assert "referenced by legislations" in response.json()["message"]

    async def test_list_categories_filtered_by_state(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)
        state = await _create_state(admin_client, country["id"])
        await _create_category(admin_client, state["id"])

        scoped = await admin_client.get(CATEGORIES, params={"state_id": state["id"]})
        everything = await admin_client.get(CATEGORIES)

        assert scoped.status_code == 200, scoped.text
        assert scoped.json()["total"] == 1
        assert everything.json()["total"] >= 1

    async def test_patch_legislation_and_search(self, admin_client: AsyncClient) -> None:
        country = await _create_country(admin_client)
        category = await _create_category(admin_client)
        created = await admin_client.post(
            LEGISLATIONS,
            json={
                "code": "zz-act",
                "name": "An Act",
                "category_of_law_id": category["id"],
                "country_id": country["id"],
            },
        )
        legislation = created.json()

        patched = await admin_client.patch(
            f"{LEGISLATIONS}/{legislation['id']}",
            json={"name": "The Renamed Act, 1950", "effective_date": "1950-01-26"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["name"] == "The Renamed Act, 1950"
        assert patched.json()["effective_date"] == "1950-01-26"

        found = await admin_client.get(LEGISLATIONS, params={"search": "Renamed"})
        assert found.json()["total"] == 1

    async def test_rule_lifecycle_then_parent_delete(self, admin_client: AsyncClient) -> None:
        """Once the child rule is gone, the legislation can be deleted."""
        country = await _create_country(admin_client)
        category = await _create_category(admin_client)
        legislation = (
            await admin_client.post(
                LEGISLATIONS,
                json={
                    "code": "zz-act",
                    "name": "An Act",
                    "category_of_law_id": category["id"],
                    "country_id": country["id"],
                },
            )
        ).json()

        rule = (
            await admin_client.post(
                RULES,
                json={
                    "code": "zz-act-r1",
                    "name": "A Rule",
                    "legislation_id": legislation["id"],
                    "country_id": country["id"],
                },
            )
        ).json()

        patched = await admin_client.patch(
            f"{RULES}/{rule['id']}", json={"name": "A Renamed Rule", "is_active": False}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["name"] == "A Renamed Rule"
        assert patched.json()["is_active"] is False

        blocked = await admin_client.delete(f"{LEGISLATIONS}/{legislation['id']}")
        assert blocked.status_code == 409

        assert (await admin_client.delete(f"{RULES}/{rule['id']}")).status_code == 204
        assert (
            await admin_client.delete(f"{LEGISLATIONS}/{legislation['id']}")
        ).status_code == 204

    async def test_task_type_duplicate_name_returns_409(self, admin_client: AsyncClient) -> None:
        await admin_client.post(TASK_TYPES, json={"code": "rf", "name": "Return Filing"})

        response = await admin_client.post(
            TASK_TYPES, json={"code": "rf2", "name": "Return Filing"}
        )

        assert response.status_code == 409, response.text

    async def test_delete_task_type(self, admin_client: AsyncClient) -> None:
        created = await admin_client.post(
            TASK_TYPES, json={"code": "rf", "name": "Return Filing"}
        )
        task_type_id = created.json()["id"]

        assert (await admin_client.delete(f"{TASK_TYPES}/{task_type_id}")).status_code == 204
        assert (await admin_client.get(f"{TASK_TYPES}/{task_type_id}")).status_code == 404
