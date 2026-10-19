from __future__ import annotations
import json, time, uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

QUIET_START, QUIET_END = 22, 8

@dataclass
class Fact:
    value: Any
    source: str
    observed_at: str
    confidence: float = 1.0

@dataclass
class Decision:
    decision_id: str
    viewer_id: str
    trigger: dict
    goal: dict | None
    action: str
    dialect: dict
    content: list[str]
    confidence: float
    confidence_reason: str
    evidence: list[dict]
    assumptions: list[str]
    conflicts: list[dict]
    checks: dict
    decided_in_ms: int
    status: str
    reason: str = ""

class MockModelProvider:
    """Deterministic model adapter. The core logic does not trust model assertions as evidence."""
    def choose_title_ids(self, titles: list[dict], limit: int = 3) -> list[str]:
        return [t["title_id"] for t in titles[:limit]]

class OneUserOneAgent:
    def __init__(self, data_dir: str | Path, state_dir: str | Path, model=None):
        self.data_dir, self.state_dir = Path(data_dir), Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.model = model or MockModelProvider()
        self.events = self._load("events.json")
        self.profiles = self._load("profiles.json")
        self.catalogue = self._load("catalogue.json")
        self.goals = self._load("goals.json")
        self.interventions = self._load("interventions.json")
        self.holdout = set(self._load("holdout.json"))
        self.seen_triggers: set[str] = set()
        self.actions: list[dict] = []
        self.decisions: list[dict] = []
        self.outcomes: list[dict] = []

    def _load(self, name):
        p = self.data_dir / name
        return json.loads(p.read_text()) if p.exists() else []

    def _state_path(self, viewer_id):
        return self.state_dir / f"{viewer_id}.json"

    def state(self, viewer_id):
        p = self._state_path(viewer_id)
        if p.exists(): return json.loads(p.read_text())
        return {"viewer_id": viewer_id, "facts": {}, "active_goal": None, "decisions": [], "actions": [], "outcomes": [], "messages_today": 0, "last_message_date": None, "learned": []}

    def _save_state(self, state):
        self._state_path(state["viewer_id"]).write_text(json.dumps(state, indent=2))

    @staticmethod
    def _dt(value):
        if not value: return None
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError): return None

    def _viewer_facts(self, viewer_id, trigger):
        events = [e for e in self.events if e.get("viewer_id") == viewer_id]
        # Do not let a late event with a wrong device clock override receipt-time ordering.
        events.sort(key=lambda e: self._dt(e.get("received_at")) or datetime.min.replace(tzinfo=timezone.utc))
        profile_rows = [p for p in self.profiles if p.get("viewer_id") == viewer_id]
        profile = max(profile_rows, key=lambda p: p.get("snapshot_at", ""), default={})
        app_dialect = trigger.get("app_dialect") or trigger.get("dialect")
        profile_dialect = profile.get("preferred_dialect")
        campaign_dialect = trigger.get("campaign_dialect")
        conflicts = []
        # Current app setting on the trigger is the most direct evidence of what the viewer sees.
        dialect = app_dialect or profile_dialect or campaign_dialect
        dialect_source = "app_setting" if app_dialect else ("profile_snapshot" if profile_dialect else "campaign_link")
        for source, value in [("profile", profile_dialect), ("campaign", campaign_dialect)]:
            if value and dialect and value != dialect:
                conflicts.append({"fact": "dialect", "chosen": dialect, "chosen_source": dialect_source, "conflicting_source": source, "conflicting_value": value})
        facts = {
            "dialect": Fact(dialect, dialect_source, trigger.get("received_at", ""), 0.95 if app_dialect else 0.65),
            "subscription_status": Fact(profile.get("subscription_status", "unknown"), "profile_snapshot", profile.get("snapshot_at", ""), 0.7),
            "events": Fact(events, "event_stream", trigger.get("received_at", ""), 0.9),
        }
        for f, obj in facts.items():
            facts[f] = asdict(obj)
        return facts, events, profile, conflicts

    def _goal_for(self, viewer_id, events, profile, now):
        paid = profile.get("subscription_status") == "paid" or any(e.get("event_type") == "purchase" for e in events)
        played_full = any(e.get("event_type") == "episode_completed" for e in events)
        signed_up = profile.get("signup_at") or next((e.get("received_at") for e in events if e.get("event_type") == "signup"), None)
        for goal in self.goals:
            gid = goal.get("goal_id")
            if gid == "first_paid_plan_7d" and (paid or not signed_up): continue
            if gid == "first_full_episode_3d" and (played_full or not signed_up): continue
            if gid not in ("first_paid_plan_7d", "first_full_episode_3d"): continue
            start = self._dt(signed_up) or now
            days = 7 if gid == "first_paid_plan_7d" else 3
            deadline = start + timedelta(days=days)
            if now <= deadline:
                return {"id": gid, "deadline": deadline.isoformat(), "success_signal": "purchase" if gid == "first_paid_plan_7d" else "episode_completed", "rule_version": goal.get("rule_version", "v1")}
        return None

    def _eligible_titles(self, dialect, now):
        output=[]
        for title in self.catalogue:
            if dialect not in title.get("dialects", []): continue
            start, end = self._dt(title.get("available_from")), self._dt(title.get("available_until"))
            if start and now < start: continue
            if end and now > end: continue
            output.append(title)
        return sorted(output, key=lambda t: (t.get("popularity", 0), t.get("title_id", "")), reverse=True)

    def decide(self, trigger: dict) -> dict:
        started = time.perf_counter()
        viewer_id = trigger["viewer_id"]
        event_id = str(trigger.get("event_id") or trigger.get("trigger_id") or f"{viewer_id}:{trigger.get('received_at')}:{trigger.get('event_type')}")
        now = self._dt(trigger.get("received_at")) or datetime.now(timezone.utc)
        state = self.state(viewer_id)
        if event_id in state.get("processed_trigger_ids", []):
            return {"decision_id": str(uuid.uuid4()), "viewer_id": viewer_id, "action": "NONE", "status": "DUPLICATE_IGNORED", "reason": "Trigger already processed", "checks": {"passed": ["idempotency"], "failed": []}}
        facts, events, profile, conflicts = self._viewer_facts(viewer_id, trigger)
        # Use receipt timestamps for relevant signals, and include the trigger itself in evidence.
        recent_events = [e for e in events if (self._dt(e.get("received_at")) or now) <= now + timedelta(minutes=1)]
        goal = self._goal_for(viewer_id, recent_events, profile, now)
        dialect = facts["dialect"]["value"]
        checks_passed, checks_failed = ["idempotency", "goal_rule", "dialect_resolution"], []
        action, content, reason = "NONE", [], "No eligible measurable goal or insufficient evidence"
        evidence = [{"ref": f"event:{e.get('event_id', e.get('event_type','unknown'))}", "source": "event_stream", "freshness": e.get("received_at"), "event_type": e.get("event_type")} for e in recent_events[-8:]]
        if goal:
            checks_passed.append("goal_eligibility")
            if not dialect:
                checks_failed.append("dialect_available")
                reason = "No reliable dialect evidence; abstained"
            else:
                titles = self._eligible_titles(dialect, now)
                if len(titles) >= 3:
                    try:
                        content = self.model.choose_title_ids(titles, 3)
                        # Validate model output independently against the filtered catalogue.
                        valid_ids = {t["title_id"] for t in titles}
                        if len(content) != 3 or len(set(content)) != 3 or not set(content).issubset(valid_ids):
                            raise ValueError("provider returned invalid title IDs")
                        action, reason = "HOME_PAGE", "Eligible goal and at least three currently available titles in the resolved app dialect"
                        checks_passed.extend(["content_dialect", "content_availability", "minimum_three_titles", "provider_output_validated"])
                        evidence.extend({"ref": f"catalogue:{t['title_id']}", "source": "catalogue", "freshness": t.get("catalogue_updated_at", "unknown")} for t in titles if t["title_id"] in content)
                    except Exception as exc:
                        content, action = [], "NONE"
                        checks_failed.append("provider_available")
                        reason = f"Provider failed; safely abstained ({type(exc).__name__})"
                else:
                    checks_failed.append("minimum_three_titles")
                    reason = "Fewer than three eligible titles; abstained"
        # A paid purchase immediately invalidates the acquisition goal, regardless of stale profile.
        if any(e.get("event_type") == "purchase" for e in recent_events) and goal and goal["id"] == "first_paid_plan_7d":
            goal, action, content, reason = None, "NONE", [], "Purchase event observed; acquisition goal no longer eligible"
            checks_passed.append("purchase_recheck")
        # This demo only uses homepage actions; messaging constraints are checked before any message is possible.
        if action.startswith("MESSAGE"):
            local_hour = now.hour
            if local_hour >= QUIET_START or local_hour < QUIET_END: action, reason = "NONE", "Quiet hours"
            checks_failed.append("messaging_policy")
        elapsed = int((time.perf_counter()-started)*1000)
        decision = Decision(
            decision_id=f"D-{uuid.uuid4().hex[:10]}", viewer_id=viewer_id,
            trigger={"event": trigger.get("event_type", "app_open"), "event_id": event_id, "received_at": trigger.get("received_at"), "event_age_s": trigger.get("event_age_s", 0)},
            goal=goal, action=action, dialect={"used": dialect, "source": facts["dialect"]["source"], "conflicts": conflicts}, content=content,
            confidence=0.82 if action != "NONE" else 0.55,
            confidence_reason="Goal eligibility is derived from event/profile rules; title dialect and availability are checked against catalogue" if action != "NONE" else reason,
            evidence=evidence, assumptions=["Synthetic input timestamps are parseable; missing data is not interpreted as proof of eligibility"], conflicts=conflicts,
            checks={"passed": checks_passed, "failed": checks_failed}, decided_in_ms=elapsed,
            status="PUBLISHED" if action != "NONE" else "NO_ACTION", reason=reason)
        result=asdict(decision)
        state["facts"] = facts
        state["active_goal"] = goal
        state.setdefault("decisions", []).append(result)
        state.setdefault("processed_trigger_ids", []).append(event_id)
        state["processed_trigger_ids"] = state["processed_trigger_ids"][-10000:]
        state.setdefault("actions", []).append({"decision_id": result["decision_id"], "action": action, "content": content, "at": trigger.get("received_at")})
        state["learned"] = state.get("learned", [])
        self._save_state(state)
        self.decisions.append(result)
        if action != "NONE": self.actions.append({"decision_id": result["decision_id"], "viewer_id": viewer_id, "action": action, "content": content, "at": trigger.get("received_at")})
        return result

    def judge_outcomes(self):
        for decision in self.decisions:
            goal=decision.get("goal")
            if not goal: continue
            viewer=decision["viewer_id"]
            signal=goal["success_signal"]
            deadline=self._dt(goal["deadline"])
            matching=[e for e in self.events if e.get("viewer_id")==viewer and e.get("event_type")==signal]
            before=[e for e in matching if deadline and self._dt(e.get("received_at")) and self._dt(e.get("received_at")) <= deadline]
            status="SUCCEEDED" if before else ("INCONCLUSIVE" if deadline is None else "FAILED")
            outcome={"decision_id": decision["decision_id"], "viewer_id": viewer, "goal_id": goal["id"], "signal": signal, "status": status, "attributable": False, "evidence": [e.get("event_id", signal) for e in before], "note": "Observed success is not causal attribution; randomized holdout is used for impact."}
            self.outcomes.append(outcome)
            st=self.state(viewer); st.setdefault("outcomes", []).append(outcome); st.setdefault("learned", []).append({"goal_id":goal["id"],"outcome":status}); self._save_state(st)
        return self.outcomes

    def impact_report(self):
        # Intent-to-treat: compare randomized assigned groups, not served vs unserved viewers.
        viewers={e.get("viewer_id") for e in self.events}
        outcomes_by_viewer={}
        for o in self.outcomes:
            outcomes_by_viewer.setdefault(o["viewer_id"], []).append(o)
        def rate(group):
            statuses=[o["status"] for v in group for o in outcomes_by_viewer.get(v, [])]
            judged=[s for s in statuses if s in ("SUCCEEDED", "FAILED")]
            return (sum(s=="SUCCEEDED" for s in judged)/len(judged) if judged else None, len(judged))
        treatment=viewers-self.holdout; control=viewers & self.holdout
        tr,tn=rate(treatment); cr,cn=rate(control)
        return {"method":"viewer-level randomized holdout; compare assigned groups, not served vs unserved", "treatment_viewers":len(treatment),"holdout_viewers":len(control),"treatment_success_rate":tr,"treatment_judged_n":tn,"holdout_success_rate":cr,"holdout_judged_n":cn,"absolute_difference":(tr-cr if tr is not None and cr is not None else None),"warning":"Synthetic demonstration only. Small samples, incomplete goal attribution and non-random/missing holdout assignments can make estimates unreliable."}
