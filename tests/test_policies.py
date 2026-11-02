"""Whole-task evaluation gates promotion; runtime selection and rollback use the same policies."""

from uuid import UUID, uuid4

from dispatcher.policies import pick_variant
from dispatcher.policy_contracts import Experiment
from test_access import invite_user
from test_integration import event, ingest


def setup_experiment(system):
    """Create two compatible aliases without naming or calling real provider models."""
    client = system["client"]
    experiment = {
        "id": str(uuid4()),
        "name": "Synthetic comparison",
        "app": "trader",
        "environment": "test",
        "seed": "fixture",
        "baseline": "baseline",
        "minimum_tasks": 2,
        "maximum_latency_ms": "1000",
        "currency": "USD",
        "variants": [
            {"name": "baseline", "model": "model-a"},
            {"name": "candidate", "model": "model-b"},
        ],
    }
    result = client.post("/api/experiments", json=experiment)
    assert result.status_code == 201, result.text
    config = {
        "id": "chat",
        "app": "trader",
        "environment": "test",
        "allowed_models": ["model-a", "model-b"],
        "fallbacks": ["model-a"],
        "required_capabilities": ["tools"],
        "model_capabilities": {"model-a": ["tools"], "model-b": ["tools"]},
        "experiment_id": experiment["id"],
    }
    result = client.put("/api/policies", json={"config": config})
    assert result.status_code == 200, result.text
    return Experiment.model_validate(experiment), config


def assigned(system, experiment, count=2):
    """Choose fixture IDs before creating exactly the required assignments."""
    variants = {"baseline": 0, "candidate": 0}
    result = []
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    while min(variants.values()) < count:
        task_id = uuid4()
        variant = pick_variant(experiment, system["owner"].tenant_id, task_id)
        if variants[variant.name] == count:
            continue
        body = {"model": "model-a", "task_id": str(task_id)}
        response = system["client"].post("/api/policies/route", json=body, headers=headers)
        assert response.status_code == 200, response.text
        route = response.json()
        assert (
            route == system["client"].post("/api/policies/route", json=body, headers=headers).json()
        )
        variants[variant.name] += 1
        result.append(route)
    return result


def outcome(system, route, **updates):
    """Report final app-attested quality and fee allocation for one assignment."""
    body = {
        "assignment_id": route["assignment_id"],
        "app": "trader",
        "environment": "test",
        "status": "completed",
        "quality": "0.95",
        "duration_ms": "100",
        "coverage_complete": True,
        "fees_accounted": True,
        "additional_cost": "0.01",
        "currency": "USD",
        "evaluator": "synthetic-app-score",
        **updates,
    }
    return system["client"].post(
        "/api/experiments/outcomes",
        json=body,
        headers={"Authorization": "Bearer " + system["key"]["secret"]},
    )


def evidence(system, route, unknown=False):
    """Record inference, failed retry and evaluator spend as separate physical attempts."""
    tags = {
        key: route[key]
        for key in (
            "experiment_id",
            "assignment_id",
            "variant",
            "requested_model",
            "policy_version",
        )
    }
    price = "1" if route["variant"] == "baseline" else "0.2"
    rows = [
        event(
            **tags,
            resource_kind="llm",
            model=route["model"],
            reported_cost=cost,
            reported_currency="USD",
            status=status,
            usage_category=category,
        )
        for cost, status, category in (
            (price, "success", "runtime"),
            ("0.1", "error", "runtime"),
            ("0.05", "success", "evaluation"),
        )
    ]
    if unknown:
        rows[0].pop("reported_cost")
        rows[0].pop("reported_currency")
    response = ingest(system, rows)
    assert response.status_code == 202, response.text


def test_policy_assignment_full_cost_promotion_and_effective_rollback(system):
    client = system["client"]
    experiment, config = setup_experiment(system)
    routes = assigned(system, experiment)
    promotion = {"variant": "candidate", "policy_id": "chat", "revision": 1}
    path = f"/api/experiments/{experiment.id}"
    assert client.post(path + "/promote", json=promotion).status_code == 409
    for route in routes:
        evidence(system, route)
        assert outcome(system, route).status_code == 202
        assert outcome(system, route).json()["inserted"] is False
    results = client.get(path).json()
    candidate = next(row for row in results["variants"] if row["variant"] == "candidate")
    assert candidate["attempts"] == 6
    assert candidate["evaluation_cost"] == "0.10"
    assert candidate["eligible"] and not candidate["proven_savings"]
    from decimal import Decimal

    assert Decimal(candidate["cost_per_success"]) == Decimal("0.36")
    assert Decimal(candidate["observed_savings_per_success"]) == Decimal("0.8")
    result = client.post(path + "/promote", json=promotion)
    assert result.status_code == 200, result.text
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    route = client.post(
        "/api/policies/route", json={"model": "model-a", "task_id": str(uuid4())}, headers=headers
    ).json()
    assert route["model"] == "model-b" and route["policy_version"] == "chat:2"
    assert "experiment_id" not in route
    history = client.get("/api/policies/chat/history").json()
    assert history[0]["action"].startswith("promote:")
    assert history[0]["evidence"]["variants"]
    assert (
        client.post(
            "/api/policies/chat/rollback", json={"revision": 2, "target_revision": 1}
        ).json()["revision"]
        == 3
    )
    assert client.get("/api/policies").json()[0]["config"]["experiment_id"] == str(experiment.id)
    assert client.put("/api/policies", json={"config": config, "revision": 1}).status_code == 409


def test_missing_cost_coverage_or_quality_blocks_promotion(system):
    client = system["client"]
    experiment, _ = setup_experiment(system)
    routes = assigned(system, experiment)
    for route in routes:
        candidate = route["variant"] == "candidate"
        evidence(system, route, unknown=candidate)
        assert (
            outcome(
                system,
                route,
                coverage_complete=not candidate,
                fees_accounted=not candidate,
                quality="0.5" if candidate else "1",
            ).status_code
            == 202
        )
    path = f"/api/experiments/{experiment.id}"
    candidate = next(
        row for row in client.get(path).json()["variants"] if row["variant"] == "candidate"
    )
    assert not candidate["eligible"] and not candidate["proven_savings"]
    assert "Unknown cost or mixed currencies" in candidate["reasons"]
    assert "Coverage or fee allocation is incomplete" in candidate["reasons"]
    assert (
        client.post(
            path + "/promote", json={"variant": "candidate", "policy_id": "chat", "revision": 1}
        ).status_code
        == 409
    )
    assert outcome(system, routes[0], quality="0").status_code == 409


def test_policy_compatibility_and_authorization(system):
    client = system["client"]
    experiment, config = setup_experiment(system)
    assert (
        client.put(
            "/api/policies", json={"revision": 1, "config": {**config, "model_capabilities": {}}}
        ).status_code
        == 422
    )
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    assert (
        client.post(
            "/api/policies/route",
            json={"model": "unapproved", "task_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/experiments/{experiment.id}",
            headers={"X-Tenant-ID": str(system["other"].tenant_id)},
        ).status_code
        == 403
    )
    route = assigned(system, experiment, 1)[0]
    assert outcome(system, route, app="another-app").status_code == 403
    wrong_assignment = event(
        experiment_id=str(experiment.id), assignment_id=str(UUID(int=1)), variant="candidate"
    )
    assert ingest(system, [wrong_assignment]).status_code == 403
    session, _, _ = invite_user(system, "member")
    client.cookies.set("dispatcher_session", session)
    assert client.get("/api/policies").status_code == 403
    assert client.get("/api/experiments").status_code == 403
