import pathlib
import unittest


WORKFLOW_PATH = pathlib.Path(__file__).parents[1] / ".github" / "workflows" / "morning.yml"


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_primary_and_recovery_runs_are_scheduled_at_kst_0730_0740_0750(self):
        self.assertIn('- cron: "30,40,50 22 * * *"', self.workflow)

    def test_overlapping_runs_are_serialized(self):
        self.assertIn("concurrency:", self.workflow)
        self.assertIn("group: morning-brief-delivery", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_latest_remote_state_is_pulled_before_delivery(self):
        pull_index = self.workflow.index("git pull --ff-only origin main")
        delivery_index = self.workflow.index("run: python main.py")

        self.assertLess(pull_index, delivery_index)

    def test_unit_tests_run_before_delivery(self):
        test_index = self.workflow.index(
            "run: python -m unittest discover -s tests -q"
        )
        delivery_index = self.workflow.index("run: python main.py")

        self.assertLess(test_index, delivery_index)

    def test_public_incremental_state_is_staged_before_change_check(self):
        self.assertIn(
            "git add data/seen_notices.json data/delivery_state.json",
            self.workflow,
        )
        self.assertIn(
            "git diff --cached --quiet -- data/seen_notices.json data/delivery_state.json",
            self.workflow,
        )
        self.assertNotIn("data/discord_assignments.json", self.workflow)

    def test_calendar_secret_and_non_secret_location_are_separated(self):
        self.assertIn("CALENDAR_ICS_URLS: ${{ secrets.CALENDAR_ICS_URLS }}", self.workflow)
        self.assertIn("FIXED_TIMETABLE_JSON: ${{ secrets.FIXED_TIMETABLE_JSON }}", self.workflow)
        self.assertIn("MARKET_HOLDINGS_KR: ${{ secrets.MARKET_HOLDINGS_KR }}", self.workflow)
        self.assertIn("MARKET_HOLDINGS_US: ${{ secrets.MARKET_HOLDINGS_US }}", self.workflow)
        self.assertIn(
            "BRIEF_LOCATION_NAME: ${{ secrets.BRIEF_LOCATION_NAME || vars.BRIEF_LOCATION_NAME }}",
            self.workflow,
        )
        self.assertIn(
            "BRIEF_LATITUDE: ${{ secrets.BRIEF_LATITUDE || vars.BRIEF_LATITUDE }}",
            self.workflow,
        )
        self.assertIn(
            "BRIEF_LONGITUDE: ${{ secrets.BRIEF_LONGITUDE || vars.BRIEF_LONGITUDE }}",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
