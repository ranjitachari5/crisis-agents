from fastapi.testclient import TestClient

from app.main import create_app


def client(settings):
    return TestClient(create_app(settings))


def test_full_api_flow(settings):
    with client(settings) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.post("/api/simulation/start").json()["status"] == "running"
        assert c.post("/api/simulation/start").status_code == 409
        assert c.post("/api/simulation/pause").json()["status"] == "paused"
        s = c.post("/api/simulation/step", json={"ticks": 2}).json()
        assert s["tick"] == 2 and s["allocation"]["version"] >= 1
        assert len(c.get("/api/agents").json()) == 6
        assert c.get("/api/agents/hospital_agent").json()["recent_messages"]
        assert c.get("/api/agents/nope").status_code == 422
        r = c.post("/api/events/inject", json={"event_type": "flood_warning", "params": {"severity": 2}})
        assert r.status_code == 200 and r.json()["negotiation"]
        bad = c.post("/api/events/inject", json={"event_type": "flood_warning", "params": {"severity": 9}})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_EVENT_PARAMS"
        inc = c.post("/api/events/inject-fake", json={"kind": "false_capacity_drop"}).json()
        assert inc["decision"] == "quarantined"
        assert c.get("/api/trust/incidents").json()
        assert c.put("/api/simulation/fairness", json={"value": 0.9}).json()["fairness"] == 0.9
        assert c.put("/api/simulation/fairness", json={"value": 2}).status_code == 422
        h = c.get("/api/negotiation/history").json()
        assert h["messages"] and h["negotiations"]
        cur = c.get("/api/allocations/current").json()
        v = c.post("/api/allocations/validate", json={"allocation": cur["agreement"]["allocation"]}).json()
        assert v["valid"]
        denied = c.post("/api/commander/override", json={"allocation": {"hospital_agent": 90},
                                                         "reason": "testing", "authorization": "wrong"})
        assert denied.status_code == 403
        assert c.post("/api/commander/agents/telecom_agent/isolate", json={"reason": "test"}).json()["isolated"]
        e = c.post("/api/commander/explain", json={"question": "why?"}).json()
        assert e["source"] == "deterministic_template" and e["text"]
        assert c.get("/api/audit/logs").json()
        assert c.get("/api/twin/graph").json()["nodes"]
        assert c.get("/api/evaluation/plan").json()["metrics"]
        assert c.post("/api/allocations/commit", json={"proposal_id": "prop-missing"}).status_code == 404


def test_websocket_snapshot_and_ping(settings):
    with client(settings) as c:
        c.post("/api/simulation/start")
        with c.websocket_connect("/ws/simulation") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "snapshot" and snap["data"]["messages"]
            ws.send_json({"type": "ping"})
            while True:
                msg = ws.receive_json()
                if msg["type"] == "pong":
                    break
