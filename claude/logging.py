# utils/logging.py
from datetime import datetime

audit_logs = []

def add_audit(msg, atype="info", en_text="", shared_stats=None):
    global audit_logs
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"<div>[{ts}] {msg}{('<br>' + en_text) if en_text else ''}</div>"
    audit_logs.append(entry)
    if len(audit_logs) > 300:
        audit_logs.pop(0)
    if shared_stats is not None:
        shared_stats["live_audit"] = "".join(audit_logs)
