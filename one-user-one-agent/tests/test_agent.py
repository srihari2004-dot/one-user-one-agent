import json, tempfile, unittest
from pathlib import Path
from agent.core import OneUserOneAgent, MockModelProvider

ROOT=Path(__file__).resolve().parents[1]
class BrokenModel:
    def choose_title_ids(self, titles, limit=3): raise RuntimeError("mock provider outage")

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.state=Path(self.tmp.name)/"state"
        self.agent=OneUserOneAgent(ROOT/"data", self.state)
        self.trigger={"event_id":"test-1","viewer_id":"V1001","event_type":"app_open","received_at":"2026-10-19T10:00:01Z","app_dialect":"d1"}
    def tearDown(self): self.tmp.cleanup()
    def test_duplicate_trigger_is_idempotent(self):
        first=self.agent.decide(self.trigger); second=self.agent.decide(self.trigger)
        self.assertEqual(first["action"], "HOME_PAGE")
        self.assertEqual(second["status"], "DUPLICATE_IGNORED")
    def test_conflicting_dialect_uses_app_setting_and_records_conflict(self):
        t={**self.trigger,"event_id":"conflict","campaign_dialect":"d2"}
        d=self.agent.decide(t)
        self.assertEqual(d["dialect"]["used"],"d1")
        self.assertTrue(d["conflicts"])
    def test_provider_failure_degrades_safely(self):
        agent=OneUserOneAgent(ROOT/"data",Path(self.tmp.name)/"broken",model=BrokenModel())
        # Provider failure should never crash the decision loop or cause an unsafe action.
        decision=agent.decide(self.trigger)
        self.assertEqual(decision["action"], "NONE")
        self.assertIn("provider_available", decision["checks"]["failed"])
    def test_corrected_goal_rule_is_loaded_for_new_agent(self):
        data=Path(self.tmp.name)/"data"; data.mkdir()
        for f in (ROOT/"data").glob("*.json"): (data/f.name).write_text(f.read_text())
        goals=json.loads((data/"goals.json").read_text()); goals[0]["rule_version"]="v2-corrected"
        (data/"goals.json").write_text(json.dumps(goals))
        agent=OneUserOneAgent(data,Path(self.tmp.name)/"corrected")
        d=agent.decide(self.trigger)
        self.assertEqual(d["goal"]["rule_version"],"v2-corrected")

if __name__=="__main__": unittest.main()
