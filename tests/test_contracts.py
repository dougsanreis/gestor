"""Contract validation and breaking-change detection.

These tests encode the behaviour that stops a backend change from silently
breaking a panel.
"""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core.contracts import (
    BREAKING,
    COMPATIBLE,
    IDENTICAL,
    Contract,
    ContractRegistry,
    compatibility,
    validate,
)
from syra_core.errors import ContractIncompatible, ContractUnknown, ContractViolation

USER_SCHEMA = {
    "type": "object",
    "required": ["id", "email"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "email": {"type": "string", "format": "email"},
        "age": {"type": "integer", "minimum": 0, "maximum": 150},
        "role": {"type": "string", "enum": ["admin", "member"]},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
}


class TestValidation(unittest.TestCase):
    def test_valid_payload_has_no_violations(self) -> None:
        payload = {
            "id": "3f2b1c4d-5e6f-4a8b-9c0d-1e2f3a4b5c6d",
            "email": "a@b.co",
            "age": 30,
            "role": "admin",
            "tags": ["x"],
        }
        self.assertEqual(validate(USER_SCHEMA, payload), [])

    def test_missing_required_is_pointed_at_exactly(self) -> None:
        violations = validate(USER_SCHEMA, {"id": "x"})
        codes = {item.code for item in violations}
        self.assertIn("REQUIRED_MISSING", codes)
        pointers = {item.pointer for item in violations}
        self.assertIn("$.email", pointers)

    def test_all_violations_are_reported_not_just_the_first(self) -> None:
        violations = validate(
            USER_SCHEMA,
            {"id": "nope", "email": "nope", "age": 900, "role": "wizard"},
        )
        codes = {item.code for item in violations}
        self.assertIn("FORMAT_MISMATCH", codes)
        self.assertIn("MAXIMUM", codes)
        self.assertIn("ENUM_MISMATCH", codes)
        self.assertGreaterEqual(len(violations), 4)

    def test_additional_properties_rejected_when_closed(self) -> None:
        violations = validate(
            USER_SCHEMA,
            {
                "id": "3f2b1c4d-5e6f-4a8b-9c0d-1e2f3a4b5c6d",
                "email": "a@b.co",
                "surprise": 1,
            },
        )
        self.assertEqual([item.code for item in violations], ["ADDITIONAL_PROPERTY"])

    def test_booleans_are_not_integers(self) -> None:
        violations = validate({"type": "integer"}, True)
        self.assertEqual(violations[0].code, "TYPE_MISMATCH")

    def test_integer_satisfies_number(self) -> None:
        self.assertEqual(validate({"type": "number"}, 7), [])

    def test_nullable_allows_none(self) -> None:
        self.assertEqual(validate({"type": "string", "nullable": True}, None), [])
        self.assertEqual(len(validate({"type": "string"}, None)), 1)

    def test_nested_pointer_addresses_the_leaf(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["qty"],
                        "properties": {"qty": {"type": "integer"}},
                    },
                }
            },
        }
        violations = validate(schema, {"items": [{"qty": 1}, {"qty": "two"}]})
        self.assertEqual(violations[0].pointer, "$.items[1].qty")

    def test_any_of_accepts_either_shape(self) -> None:
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(validate(schema, "x"), [])
        self.assertEqual(validate(schema, 3), [])
        self.assertEqual(validate(schema, [])[0].code, "ANY_OF_MISMATCH")

    def test_unique_items(self) -> None:
        schema = {"type": "array", "uniqueItems": True}
        self.assertEqual(validate(schema, [1, 2]), [])
        self.assertEqual(validate(schema, [1, 1])[0].code, "UNIQUE_ITEMS")


class TestContract(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = Contract(
            name="user", version="1.0.0", schema=USER_SCHEMA
        )

    def test_enforce_returns_value_on_success(self) -> None:
        payload = {"id": "3f2b1c4d-5e6f-4a8b-9c0d-1e2f3a4b5c6d", "email": "a@b.co"}
        self.assertIs(self.contract.enforce(payload), payload)

    def test_enforce_raises_with_remediation(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            self.contract.enforce({}, role="request")
        error = caught.exception
        self.assertEqual(error.contract, "user@1.0.0")
        self.assertTrue(error.violations)
        self.assertIn("$.id", error.remediation or "")

    def test_fingerprint_is_content_addressed(self) -> None:
        same = Contract(name="other", version="9.9.9", schema=dict(USER_SCHEMA))
        self.assertEqual(self.contract.fingerprint, same.fingerprint)


class TestCompatibility(unittest.TestCase):
    def test_identical_schemas(self) -> None:
        self.assertEqual(
            compatibility(USER_SCHEMA, dict(USER_SCHEMA)).verdict, IDENTICAL
        )

    def test_new_required_field_breaks_consumers(self) -> None:
        evolved = dict(USER_SCHEMA)
        evolved["required"] = ["id", "email", "age"]
        report = compatibility(USER_SCHEMA, evolved)
        self.assertEqual(report.verdict, BREAKING)
        self.assertFalse(report.is_safe)
        self.assertEqual(report.breaking[0]["change"], "REQUIRED_ADDED")

    def test_removed_property_breaks_consumers(self) -> None:
        evolved = {**USER_SCHEMA, "properties": {
            key: value for key, value in USER_SCHEMA["properties"].items()
            if key != "age"
        }}
        report = compatibility(USER_SCHEMA, evolved)
        self.assertEqual(report.verdict, BREAKING)
        self.assertIn(
            "PROPERTY_REMOVED", {item["change"] for item in report.breaking}
        )

    def test_narrowed_enum_breaks_consumers(self) -> None:
        evolved = {
            **USER_SCHEMA,
            "properties": {
                **USER_SCHEMA["properties"],
                "role": {"type": "string", "enum": ["admin"]},
            },
        }
        report = compatibility(USER_SCHEMA, evolved)
        self.assertEqual(report.verdict, BREAKING)

    def test_added_optional_property_is_safe(self) -> None:
        evolved = {
            **USER_SCHEMA,
            "properties": {
                **USER_SCHEMA["properties"],
                "nickname": {"type": "string"},
            },
        }
        report = compatibility(USER_SCHEMA, evolved)
        self.assertEqual(report.verdict, COMPATIBLE)
        self.assertTrue(report.is_safe)

    def test_widened_enum_is_safe(self) -> None:
        evolved = {
            **USER_SCHEMA,
            "properties": {
                **USER_SCHEMA["properties"],
                "role": {"type": "string", "enum": ["admin", "member", "guest"]},
            },
        }
        self.assertEqual(compatibility(USER_SCHEMA, evolved).verdict, COMPATIBLE)


class TestRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ContractRegistry()
        self.registry.define("user", "1.0.0", USER_SCHEMA)

    def test_unknown_contract_raises(self) -> None:
        with self.assertRaises(ContractUnknown):
            self.registry.get("nope")

    def test_latest_version_is_default(self) -> None:
        evolved = {
            **USER_SCHEMA,
            "properties": {**USER_SCHEMA["properties"], "nickname": {"type": "string"}},
        }
        self.registry.define("user", "1.1.0", evolved)
        self.assertEqual(self.registry.get("user").version, "1.1.0")
        self.assertEqual(self.registry.get("user", "1.0.0").version, "1.0.0")

    def test_breaking_registration_is_refused_by_default(self) -> None:
        breaking = {**USER_SCHEMA, "required": ["id", "email", "age"]}
        with self.assertRaises(ContractIncompatible) as caught:
            self.registry.define("user", "2.0.0", breaking)
        self.assertIn("report", caught.exception.detail)

    def test_breaking_registration_allowed_when_intended(self) -> None:
        breaking = {**USER_SCHEMA, "required": ["id", "email", "age"]}
        contract = self.registry.define(
            "user", "2.0.0", breaking, allow_breaking=True
        )
        self.assertEqual(contract.version, "2.0.0")

    def test_version_content_is_immutable(self) -> None:
        with self.assertRaises(ContractIncompatible):
            self.registry.define("user", "1.0.0", {"type": "object"})

    def test_re_registering_identical_content_is_idempotent(self) -> None:
        again = self.registry.define("user", "1.0.0", USER_SCHEMA)
        self.assertEqual(again.fingerprint, self.registry.get("user", "1.0.0").fingerprint)
        self.assertEqual(len(self.registry), 1)

    def test_ref_resolution_across_contracts(self) -> None:
        self.registry.define(
            "envelope",
            "1.0.0",
            {
                "type": "object",
                "required": ["user"],
                "properties": {"user": {"$ref": "syra://contract/user@1.0.0"}},
            },
        )
        payload = {
            "user": {"id": "3f2b1c4d-5e6f-4a8b-9c0d-1e2f3a4b5c6d", "email": "a@b.co"}
        }
        self.assertEqual(self.registry.enforce("envelope", payload), payload)

        with self.assertRaises(ContractViolation):
            self.registry.enforce("envelope", {"user": {"id": "x"}})


class TestPersistence(TempDirCase):
    def test_export_and_reload(self) -> None:
        registry = ContractRegistry()
        registry.define("user", "1.0.0", USER_SCHEMA)
        path = self.path("contracts.json")
        registry.save(path)

        restored = ContractRegistry.from_file(path)
        self.assertEqual(
            restored.get("user").fingerprint, registry.get("user").fingerprint
        )


if __name__ == "__main__":
    unittest.main()
