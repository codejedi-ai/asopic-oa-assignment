"""
Mission persistence — every mission's screenshots, text/actions, and the
SAS' transition log (for reproducible Q-learning) are written under
~/.clio/missions/<mission_id>/:

    mission.json          mission metadata (repo, goal, status, result, timestamps)
    events.jsonl          ordered log of every streamed event (text, actions, thoughts)
    screenshots/step_N.png  per-step screenshots
    dom/step_N.html       per-step DOM snapshot (for reproducibility)
    transitions.jsonl     SAS' transitions:
        S       = {screenshot_id, url, dom_sha, dom_file}
        A       = JSON of the action taken {type, selector, text, tag, url, page_url}
        S_prime = {screenshot_id, url, dom_sha, dom_file}

A global replay table is also appended to ~/.clio/data/transitions.jsonl.
"""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

MISSIONS_DIR = Path(config.CLIO_HOME) / "missions"
GLOBAL_TRANSITIONS = Path(config.DATA_DIR) / "transitions.jsonl"


def _now() -> str:
    return datetime.now().isoformat()


class MissionLogger:
    def __init__(self, mission_id: str, repo: str, goal: str, start_url: str):
        self.id = mission_id
        self.dir = MISSIONS_DIR / mission_id
        self.shots_dir = self.dir / "screenshots"
        self.dom_dir = self.dir / "dom"
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.dom_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.transitions_path = self.dir / "transitions.jsonl"
        # Continue an existing mission if one is already on disk (preserve its
        # created_at and accumulate events/transitions); else start fresh.
        existing = self.dir / "mission.json"
        prev = {}
        if existing.exists():
            try:
                prev = json.loads(existing.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        self.meta = {
            "id": mission_id,
            "repo": repo or prev.get("repo"),
            "goal": goal or prev.get("goal"),
            "start_url": start_url or prev.get("start_url"),
            "status": "running",
            "created_at": prev.get("created_at", _now()),
            "finished_at": None,
            "steps": prev.get("steps", 0),
            "result": prev.get("result"),
            "runs": prev.get("runs", 0) + 1,
        }
        if prev:
            self.log_event("mission_continued", {"goal": goal, "run": self.meta["runs"]})
        self._save_meta()

    def _save_meta(self) -> None:
        (self.dir / "mission.json").write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def update_meta(self, **kwargs) -> None:
        self.meta.update(kwargs)
        self._save_meta()

    def log_event(self, etype: str, data: Dict[str, Any]) -> None:
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": _now(), "type": etype, "data": data}) + "\n")
        except Exception as e:
            print(f"[mission_store] log_event failed: {e}")

    def save_screenshot(self, b64: Optional[str], step: int) -> Optional[str]:
        if not b64:
            return None
        sid = f"step_{step}"
        try:
            (self.shots_dir / f"{sid}.png").write_bytes(base64.b64decode(b64))
        except Exception as e:
            print(f"[mission_store] save_screenshot failed: {e}")
            return None
        return sid

    def save_state(self, step: int, url: str, screenshot_b64: Optional[str], dom: str) -> Dict[str, Any]:
        """Save the screenshot + DOM for a step and return the state dict S."""
        sid = self.save_screenshot(screenshot_b64, step)
        dom = dom or ""
        dom_sha = hashlib.sha256(dom.encode("utf-8")).hexdigest()[:16]
        dom_file = f"dom/step_{step}.html"
        try:
            (self.dom_dir / f"step_{step}.html").write_text(dom, encoding="utf-8")
        except Exception as e:
            print(f"[mission_store] save_state dom failed: {e}")
        self.update_meta(steps=step)
        return {"screenshot_id": sid, "url": url, "dom_sha": dom_sha, "dom_file": dom_file}

    def record_transition(self, s: Dict[str, Any], a: Dict[str, Any], s_prime: Dict[str, Any],
                          reward: Optional[float] = None) -> None:
        rec = {"ts": _now(), "mission_id": self.id, "S": s, "A": a, "S_prime": s_prime}
        if reward is not None:
            rec["reward"] = reward
        line = json.dumps(rec)
        try:
            with open(self.transitions_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            # global replay table
            GLOBAL_TRANSITIONS.parent.mkdir(parents=True, exist_ok=True)
            with open(GLOBAL_TRANSITIONS, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[mission_store] record_transition failed: {e}")

    def finish(self, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        self.update_meta(status=status, result=result, finished_at=_now())


def list_missions() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if MISSIONS_DIR.exists():
        for d in MISSIONS_DIR.iterdir():
            mp = d / "mission.json"
            if mp.exists():
                try:
                    out.append(json.loads(mp.read_text(encoding="utf-8")))
                except Exception:
                    pass
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


def get_mission(mission_id: str) -> Optional[Dict[str, Any]]:
    d = MISSIONS_DIR / mission_id
    mp = d / "mission.json"
    if not mp.exists():
        return None
    meta = json.loads(mp.read_text(encoding="utf-8"))

    def _read_jsonl(p: Path) -> List[Dict[str, Any]]:
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    return {
        "meta": meta,
        "events": _read_jsonl(d / "events.jsonl"),
        "transitions": _read_jsonl(d / "transitions.jsonl"),
    }


def get_screenshot_path(mission_id: str, screenshot_id: str) -> Optional[Path]:
    p = MISSIONS_DIR / mission_id / "screenshots" / f"{screenshot_id}.png"
    return p if p.exists() else None


def rename_mission(mission_id: str, title: str) -> bool:
    """Set a human-friendly title on a persisted mission."""
    mp = MISSIONS_DIR / mission_id / "mission.json"
    if not mp.exists():
        return False
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        meta["title"] = title
        mp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[mission_store] rename failed: {e}")
        return False
