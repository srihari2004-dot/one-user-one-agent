import argparse, json, time
from pathlib import Path
from .core import OneUserOneAgent

def main():
    p=argparse.ArgumentParser(description="Replay One User, One Agent synthetic OTT lifecycle triggers")
    p.add_argument("--data",default="data"); p.add_argument("--state",default="sample_run/viewer_state")
    p.add_argument("--triggers",default="data/triggers.json"); p.add_argument("--out",default="sample_run")
    args=p.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    agent=OneUserOneAgent(args.data,args.state)
    triggers=json.loads(Path(args.triggers).read_text())
    start=time.perf_counter()
    for trigger in triggers: agent.decide(trigger)
    agent.judge_outcomes(); impact=agent.impact_report()
    (out/"decisions.jsonl").write_text("".join(json.dumps(x)+"\n" for x in agent.decisions))
    (out/"actions.jsonl").write_text("".join(json.dumps(x)+"\n" for x in agent.actions))
    (out/"outcomes.jsonl").write_text("".join(json.dumps(x)+"\n" for x in agent.outcomes))
    latency={"trigger_count":len(triggers),"decision_count":len(agent.decisions),"total_replay_ms":int((time.perf_counter()-start)*1000),"max_decision_ms":max([d["decided_in_ms"] for d in agent.decisions] or [0]),"within_60_seconds":all(d["decided_in_ms"]<60000 for d in agent.decisions)}
    (out/"latency_report.json").write_text(json.dumps(latency,indent=2))
    (out/"impact_report.md").write_text("# Impact report\n\n```json\n"+json.dumps(impact,indent=2)+"\n```\n\nOutcomes are observed signals, not proof that an intervention caused the outcome. Use the randomized viewer-level holdout for the comparison; never compare served viewers against everyone else.\n")
    print(json.dumps({"decisions":len(agent.decisions),"actions":len(agent.actions),"outcomes":len(agent.outcomes),"latency":latency,"impact":impact},indent=2))
if __name__=="__main__": main()
