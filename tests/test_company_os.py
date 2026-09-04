"""Contract tests for the pure Company OS team and planning model."""

from datetime import date, timedelta
import unittest

import company_os


OBJECTIVE_CASES = {
    "release": ("Launch the next single", "The final master is delivery ready"),
    "campaign": ("Build a marketing campaign", "Grow the audience and fan list"),
    "tour": ("Route the fall tour", "Confirm every venue and show date"),
    "revenue": ("Recover missing royalty payments", "Reconcile every statement"),
    "rights": ("Clear the ownership splits", "Resolve the contract and rights gaps"),
    "creative": ("Lock the visual identity", "Approve the artwork and brand system"),
    "general": ("Build the company operating plan", "Give the owner one decision"),
}


class CompanyDefinitionTests(unittest.TestCase):
    def test_team_has_exactly_ten_ordered_seats_and_twenty_unique_capabilities(self):
        self.assertEqual(10, len(company_os.TEAM))
        self.assertEqual(
            [f"{seat:02d}" for seat in range(1, 11)],
            [member["seat"] for member in company_os.TEAM],
        )

        desk_keys = [member["key"] for member in company_os.TEAM]
        capability_keys = [
            feature["key"]
            for member in company_os.TEAM
            for feature in member["capabilities"]
        ]
        self.assertEqual(10, len(set(desk_keys)))
        self.assertTrue(all(len(member["capabilities"]) == 2 for member in company_os.TEAM))
        self.assertEqual(20, len(capability_keys))
        self.assertEqual(20, len(set(capability_keys)))
        self.assertEqual([], company_os.validate_team())

    def test_role_and_capability_definitions_are_complete_and_scoped(self):
        self.assertEqual(
            {member["key"] for member in company_os.TEAM},
            set(company_os.TEAM_BY_KEY),
        )
        self.assertEqual(20, len(company_os.FEATURE_BY_KEY))

        for member in company_os.TEAM:
            with self.subTest(desk=member["key"]):
                self.assertTrue(member["name"])
                self.assertTrue(member["role"])
                self.assertTrue(member["focus"])
                self.assertTrue(member["href"].startswith("/"))
                for feature in member["capabilities"]:
                    self.assertIs(
                        feature,
                        company_os.capability(member["key"], feature["key"]),
                    )
                    self.assertTrue(feature["name"])
                    self.assertTrue(feature["output"])
                    self.assertTrue(feature["href"].startswith("/"))

        self.assertIsNone(company_os.capability("missing_desk", "brief_to_plan"))
        self.assertIsNone(company_os.capability("manager", "track_evaluation"))


class CompanyPlanningTests(unittest.TestCase):
    TODAY = date(2026, 9, 4)

    def test_objective_routing_is_expected_and_repeatable(self):
        for expected_type, (title, success) in OBJECTIVE_CASES.items():
            with self.subTest(objective_type=expected_type):
                first = company_os.detect_objective_type(title, success)
                second = company_os.detect_objective_type(title, success)
                self.assertEqual(expected_type, first)
                self.assertEqual(first, second)

    def test_operating_plans_are_deterministic_for_fixed_inputs(self):
        for expected_type, (title, success) in OBJECTIVE_CASES.items():
            with self.subTest(objective_type=expected_type):
                first = company_os.build_operating_plan(
                    title,
                    success_condition=success,
                    target_date="2026-10-30",
                    today=self.TODAY,
                )
                second = company_os.build_operating_plan(
                    title,
                    success_condition=success,
                    target_date="2026-10-30",
                    today=self.TODAY,
                )
                self.assertEqual(first, second)
                self.assertEqual(expected_type, first["objective_type"])
                self.assertEqual(
                    list(range(1, len(first["items"]) + 1)),
                    [item["sequence"] for item in first["items"]],
                )

    def test_every_plan_item_references_a_real_role_and_its_own_capability(self):
        for objective_type, (title, success) in OBJECTIVE_CASES.items():
            plan = company_os.build_operating_plan(
                title, success_condition=success, today=self.TODAY
            )
            for item in plan["items"]:
                with self.subTest(
                    objective_type=objective_type,
                    assignee=item["assignee"],
                    capability=item["capability"],
                ):
                    member = company_os.TEAM_BY_KEY.get(item["assignee"])
                    self.assertIsNotNone(member)
                    feature = company_os.capability(
                        item["assignee"], item["capability"]
                    )
                    self.assertIsNotNone(feature)
                    self.assertEqual(member["name"], item["desk_name"])
                    self.assertEqual(feature["name"], item["feature_name"])

    def test_planning_never_falsely_assigns_or_finishes_work(self):
        forbidden_completion_fields = {
            "assigned_at",
            "completed_at",
            "delivered_at",
            "result",
            "artifact_id",
        }
        for objective_type, (title, success) in OBJECTIVE_CASES.items():
            plan = company_os.build_operating_plan(
                title, success_condition=success, today=self.TODAY
            )
            for item in plan["items"]:
                with self.subTest(
                    objective_type=objective_type, sequence=item["sequence"]
                ):
                    self.assertEqual("proposed", item["status"])
                    self.assertTrue(forbidden_completion_fields.isdisjoint(item))
                    self.assertTrue(item["required_input"])
                    self.assertTrue(item["expected_deliverable"])

    def test_release_plan_default_deadlines_follow_the_declared_sequence(self):
        plan = company_os.build_operating_plan(
            "Launch the next single", today=self.TODAY
        )
        expected_offsets = (2, 4, 6, 8, 10, 12, 14)
        self.assertEqual(
            [(self.TODAY + timedelta(days=offset)).isoformat()
             for offset in expected_offsets],
            [item["due_date"] for item in plan["items"]],
        )

    def test_target_deadlines_are_valid_and_bounded(self):
        target = date(2026, 10, 30)
        for objective_type, (title, success) in OBJECTIVE_CASES.items():
            plan = company_os.build_operating_plan(
                title,
                success_condition=success,
                target_date=target.isoformat(),
                today=self.TODAY,
            )
            due_dates = [date.fromisoformat(item["due_date"]) for item in plan["items"]]
            with self.subTest(objective_type=objective_type):
                self.assertTrue(all(self.TODAY <= due <= target for due in due_dates))

        overdue_target = (self.TODAY - timedelta(days=30)).isoformat()
        overdue_plan = company_os.build_operating_plan(
            "Route the fall tour",
            target_date=overdue_target,
            today=self.TODAY,
        )
        self.assertEqual(
            [self.TODAY.isoformat()] * len(overdue_plan["items"]),
            [item["due_date"] for item in overdue_plan["items"]],
        )

    def test_invalid_target_date_uses_the_deterministic_default_schedule(self):
        default_plan = company_os.build_operating_plan(
            "Recover missing royalty payments", today=self.TODAY
        )
        invalid_plan = company_os.build_operating_plan(
            "Recover missing royalty payments",
            target_date="not-a-date",
            today=self.TODAY,
        )
        self.assertEqual(
            [item["due_date"] for item in default_plan["items"]],
            [item["due_date"] for item in invalid_plan["items"]],
        )


if __name__ == "__main__":
    unittest.main()
