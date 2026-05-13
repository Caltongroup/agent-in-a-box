#!/usr/bin/env python3
import requests
from datetime import datetime

def load_checkpoint(agent_id: str = "archer", pb_url: str = "http://localhost:8090"):
    try:
        r = requests.get(
            f"{pb_url}/api/collections/startup_checkpoint/records",
            params={"filter": f'agent_id="{agent_id}"', "sort": "-created_at", "perPage": 1},
            timeout=3
        )
        items = r.json().get("items", [])
        return items[0] if items else None
    except Exception:
        return None

def save_checkpoint(agent_id: str, blocking_directives=None, pending_work=None, pb_url: str = "http://localhost:8090"):
    try:
        payload = {
            "agent_id": agent_id,
            "blocking_directives": blocking_directives or [],
            "pending_work": pending_work or [],
            "last_execution_id": "current"
        }
        requests.post(f"{pb_url}/api/collections/startup_checkpoint/records", json=payload, timeout=2)
    except Exception:
        pass
