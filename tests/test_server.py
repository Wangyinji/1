import tempfile
import unittest
from pathlib import Path

from server import VeritaService


class VeritaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.service = VeritaService(Path(self.temporary_directory.name) / "test.db")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_seeded_review_queue(self) -> None:
        reviews = self.service.list_cases(status="Review")
        self.assertEqual(3, len(reviews))
        self.assertEqual("Sophie Moreau", reviews[0]["name"])

    def test_standard_case_is_auto_approved_and_audited(self) -> None:
        case = self.service.create_case(
            {
                "fullName": "Camille Laurent",
                "email": "camille@example.fr",
                "country": "FR",
                "customerType": "Individual",
                "address": "16 rue Victor Hugo, Paris",
            },
            "Test user",
        )
        self.assertEqual("Approved", case["status"])
        self.assertEqual("Low", case["risk"])
        self.assertTrue(self.service.verify_audit_chain()["valid"])

    def test_business_case_requires_review(self) -> None:
        case = self.service.create_case(
            {
                "fullName": "Southern Solar",
                "email": "ops@example.au",
                "country": "AU",
                "customerType": "Small business",
                "address": "88 Market Street, Sydney",
            },
            "Test user",
        )
        self.assertEqual("Review", case["status"])
        self.assertEqual("Medium", case["risk"])

    def test_human_decision_is_persisted(self) -> None:
        case = self.service.decide_case("FR-2026-04291", "approve", "Reviewer", "Evidence checked")
        self.assertEqual("Approved", case["status"])
        self.assertTrue(self.service.verify_audit_chain()["valid"])

    def test_missing_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing required fields"):
            self.service.create_case({"fullName": "Incomplete"}, "Test user")


if __name__ == "__main__":
    unittest.main()
