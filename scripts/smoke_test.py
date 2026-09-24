#!/usr/bin/env python3
"""End-to-end smoke checks against a running CityEye Docker stack."""

from __future__ import annotations

import argparse
import json
from http.cookies import SimpleCookie
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SmokeFailure(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    headers: Any
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"Expected JSON for HTTP {self.status}: {self.body[:200]!r}") from exc


class Smoke:
    def __init__(self, backend: str, frontend: str, admin_user: str, admin_password: str) -> None:
        self.backend = backend.rstrip("/")
        self.frontend = frontend.rstrip("/")
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.passed = 0
        self.read_token: str | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
        expected: int = 200,
        byte_range: str | None = None,
        origin: str | None = None,
    ) -> Response:
        headers = {"Accept": "application/json", "X-Request-ID": "cityeye-smoke-test"}
        if origin:
            headers["Origin"] = origin
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if token is None and method == "GET":
            token = self.read_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if byte_range:
            headers["Range"] = byte_range
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                result = Response(response.status, response.headers, response.read())
        except HTTPError as exc:
            result = Response(exc.code, exc.headers, exc.read())
        except URLError as exc:
            raise SmokeFailure(f"Cannot reach {url}: {exc.reason}") from exc
        if result.status != expected:
            raise SmokeFailure(
                f"{method} {url} returned HTTP {result.status}; expected {expected}. "
                f"Response: {result.body[:300].decode(errors='replace')}"
            )
        return result

    def check(self, label: str, condition: bool, detail: str) -> None:
        if not condition:
            raise SmokeFailure(f"{label}: {detail}")
        self.passed += 1
        print(f"PASS  {label}")

    def wait(self) -> None:
        deadline = time.monotonic() + 120
        last_error = "not started"
        while time.monotonic() < deadline:
            try:
                if self.request("GET", f"{self.backend}/health/live").status == 200:
                    return
            except SmokeFailure as exc:
                last_error = str(exc)
            time.sleep(2)
        raise SmokeFailure(f"Backend did not become live within 120 seconds: {last_error}")

    def login(self, username: str, password: str) -> str:
        result = self.request(
            "POST",
            f"{self.backend}/api/auth/login",
            payload={"username": username, "password": password},
        )
        cookie = SimpleCookie()
        cookie.load(result.headers.get("Set-Cookie", ""))
        if "cityeye_session" not in cookie or "access_token" in result.json():
            raise SmokeFailure("Login must return an HttpOnly session cookie without a JSON token")
        return cookie["cityeye_session"].value

    def run(self) -> None:
        self.wait()
        live = self.request("GET", f"{self.backend}/health/live").json()
        self.check("backend liveness", live.get("status") == "ok", str(live))

        ready = self.request("GET", f"{self.backend}/health/ready").json()
        self.check("backend readiness", ready.get("status") == "ready", str(ready))
        components = ready.get("components", {})
        self.check("required database", components.get("database", {}).get("status") == "ok", str(components))
        self.check(
            "optional services are graceful",
            isinstance(components.get("ai_artifacts"), dict),
            "readiness must report optional AI artifact state without making it a required dependency",
        )

        frontend = self.request("GET", self.frontend).body.decode(errors="replace")
        self.check("frontend availability", '<div id="root"></div>' in frontend, "Vite application shell missing")
        frontend_health = self.request("GET", f"{self.frontend}/healthz").body.decode(errors="replace")
        self.check("frontend container health", "ok" in frontend_health.lower(), frontend_health)

        anonymous_session = self.request("GET", f"{self.backend}/api/auth/session").json()
        self.check(
            "authentication session",
            anonymous_session == {"auth_required": True, "user": None},
            f"unexpected anonymous session: {anonymous_session}",
        )

        proxied_login = self.request(
            "POST", f"{self.frontend}/api/auth/login", origin=self.frontend,
            payload={"username": self.admin_user, "password": self.admin_password},
        )
        self.check("same-origin login through frontend proxy", "HttpOnly" in proxied_login.headers.get("Set-Cookie", ""), "session cookie missing")
        admin_token = self.login(self.admin_user, self.admin_password)
        self.read_token = admin_token
        admin_session = self.request("GET", f"{self.backend}/api/auth/session", token=admin_token).json()
        self.check("current code authentication", admin_session.get("user", {}).get("role") == "ADMIN", str(admin_session))

        suffix = str(int(time.time()))
        operator_name = f"smoke-operator-{suffix}"
        reviewer_name = f"smoke-reviewer-{suffix}"
        operator_password = "SmokeOperator-Password-123!"
        reviewer_password = "SmokeReviewer-Password-123!"
        for username, password, role in (
            (operator_name, operator_password, "OPERATOR"),
            (reviewer_name, reviewer_password, "REVIEWER"),
        ):
            self.request(
                "POST",
                f"{self.backend}/api/users",
                token=admin_token,
                payload={"username": username, "password": password, "role": role},
                expected=201,
            )
        operator_token = self.login(operator_name, operator_password)
        reviewer_token = self.login(reviewer_name, reviewer_password)

        scenarios_payload = self.request("GET", f"{self.backend}/api/scenarios").json()
        scenarios = scenarios_payload.get("scenarios", [])
        scenario_ids = {item.get("scenario_id") for item in scenarios}
        expected_ids = {"normal_traffic", "congestion", "rainy_traffic", "stopped_vehicle", "maydan_palestine"}
        self.check("scenario listing", expected_ids <= scenario_ids, f"missing scenarios: {expected_ids - scenario_ids}")

        first_samples: dict[str, int] = {}
        event_refs: list[tuple[str, dict[str, Any]]] = []
        for scenario_id in sorted(expected_ids):
            prefix = f"{self.backend}/api/scenarios/{scenario_id}"
            summary = self.request("GET", f"{prefix}/analysis/summary").json()
            self.check(
                f"{scenario_id} analysis summary",
                summary.get("status") == "READY" and summary.get("annotated_video_available") is True,
                str(summary),
            )
            timeline = self.request("GET", f"{prefix}/analysis/timeline").json()
            frames = timeline.get("frames", [])
            self.check(f"{scenario_id} timeline", bool(frames), "timeline has no real samples")
            first_samples[scenario_id] = int(frames[0].get("active_vehicle_count", 0))

            video = self.request(
                "GET",
                f"{self.backend}/media/scenarios/{scenario_id}/annotated.mp4",
                expected=206,
                byte_range="bytes=0-1023",
            )
            self.check(
                f"{scenario_id} annotated video",
                video.headers.get_content_type() == "video/mp4" and len(video.body) > 0,
                f"content-type={video.headers.get_content_type()}, bytes={len(video.body)}",
            )

            events_payload = self.request("GET", f"{prefix}/events").json()
            events = events_payload.get("events", [])
            self.check(
                f"{scenario_id} event listing",
                events_payload.get("total") == len(events),
                str(events_payload),
            )
            for event in events:
                event_refs.append((scenario_id, event))
                evidence = event.get("evidence_image")
                if evidence:
                    filename = evidence.rsplit("/", 1)[-1]
                    image = self.request(
                        "GET",
                        f"{self.backend}/evidence/scenarios/{scenario_id}/{quote(filename)}",
                    )
                    self.check(
                        f"{scenario_id} evidence {filename}",
                        image.headers.get_content_type() == "image/jpeg" and len(image.body) > 0,
                        f"content-type={image.headers.get_content_type()}, bytes={len(image.body)}",
                    )

        self.check(
            "real initial metrics",
            first_samples.get("normal_traffic", 0) > 0
            and first_samples.get("congestion", 0) > 0
            and first_samples.get("stopped_vehicle", 0) > 0,
            f"unexpected first samples: {first_samples}",
        )

        stopped = next(
            (event for scenario, event in event_refs if scenario == "stopped_vehicle" and event.get("event_type") == "STOPPED_VEHICLE"),
            None,
        )
        self.check("stopped vehicle event details", isinstance(stopped, dict), "STOPPED_VEHICLE event missing")
        details = stopped.get("details") if stopped else None
        required_details = {
            "track_id",
            "vehicle_class",
            "stationary_duration_seconds",
            "movement_value",
            "movement_unit",
            "roi_status",
        }
        self.check(
            "stopped vehicle structured details",
            isinstance(details, dict) and required_details <= details.keys(),
            f"missing structured details: {details}",
        )

        review_scenario, review_event = next(
            ((scenario, event) for scenario, event in event_refs if event.get("status") == "PROPOSED"),
            event_refs[0] if event_refs else (None, None),
        )
        self.check("reviewable real event", bool(review_scenario and review_event), "no real scenario event is available")
        event_id = review_event["event_id"]
        review_url = f"{self.backend}/api/scenarios/{review_scenario}/events/{quote(event_id)}"

        self.request("POST", f"{review_url}/verify", expected=401)
        self.request("POST", f"{review_url}/verify", token=operator_token, expected=403)
        self.check("Verify authorization", True, "anonymous=401 and OPERATOR=403")

        verified = self.request("POST", f"{review_url}/verify", token=reviewer_token).json()
        self.check("Reviewer Verify", verified.get("status") == "VERIFIED", str(verified))
        refetched = self.request("GET", f"{self.backend}/api/scenarios/{review_scenario}/events").json()
        persisted = next(item for item in refetched.get("events", []) if item.get("event_id") == event_id)
        self.check("Verify persistence", persisted.get("status") == "VERIFIED", str(persisted))

        self.request("POST", f"{review_url}/dismiss", token=operator_token, expected=403)
        dismissed = self.request("POST", f"{review_url}/dismiss", token=admin_token).json()
        self.check("Dismiss authorization", dismissed.get("status") == "DISMISSED", str(dismissed))
        refetched = self.request("GET", f"{self.backend}/api/scenarios/{review_scenario}/events").json()
        persisted = next(item for item in refetched.get("events", []) if item.get("event_id") == event_id)
        self.check("Dismiss persistence", persisted.get("status") == "DISMISSED", str(persisted))

        print(f"\nSMOKE TEST: PASS ({self.passed} checks)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:18000")
    parser.add_argument("--frontend", default="http://127.0.0.1:15173")
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()
    try:
        Smoke(args.backend, args.frontend, args.admin_user, args.admin_password).run()
    except (SmokeFailure, KeyError, StopIteration) as exc:
        print(f"\nSMOKE TEST: FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
