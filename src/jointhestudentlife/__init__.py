"""jointhestudentlife: the official Python SDK for The Student Life.

Student events, ticket prices, city guides and student deals in 85+ cities,
from the open REST API at https://jointhestudentlife.com/api/v1
(docs: https://jointhestudentlife.com/developers).

Standard library only. The API is open: no key, no signup.

    from jointhestudentlife import TheStudentLife
    tsl = TheStudentLife()
    tsl.events(city="berlin", type="halloween")
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

__all__ = ["TheStudentLife", "TheStudentLifeError", "DEFAULT_BASE_URL", "__version__"]
__version__ = "1.0.0"
DEFAULT_BASE_URL = "https://jointhestudentlife.com"


class TheStudentLifeError(Exception):
    """An error answer from the API, or a network problem.

    ``status`` is the HTTP status (None for network errors), ``code`` the API
    error code (for example ``not_found``, ``rate_limited``, ``timeout``,
    ``network_error``) and ``body`` the parsed response body.
    """

    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body


def _query(params: Dict[str, Any]) -> str:
    clean = {}
    for k, v in params.items():
        if v is None or v == "":
            continue
        clean[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return ("?" + urllib.parse.urlencode(clean)) if clean else ""


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", "_", s)
    return re.sub(r"[^a-z0-9_-]", "", s)


class TheStudentLife:
    """Client for the The Student Life REST API.

    Retries 429 (honouring Retry-After) and, for GET requests or a POST with an
    idempotency key, 5xx answers; a plain POST is never sent twice.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0, max_retries: int = 2, user_agent: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, min(int(max_retries), 5))
        self.user_agent = user_agent or "jointhestudentlife-python/" + __version__

    # ---------- low level ----------
    def request(self, path: str, method: str = "GET", body: Any = None, headers: Optional[Dict[str, str]] = None) -> Any:
        method = method.upper()
        hdrs = {"Accept": "application/json", "User-Agent": self.user_agent}
        hdrs.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        safe = method in ("GET", "HEAD") or "Idempotency-Key" in hdrs
        attempt = 0
        while True:
            req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as res:
                    return self._parse(res.read())
            except urllib.error.HTTPError as e:
                status, retry_after, parsed = e.code, e.headers.get("Retry-After"), self._parse(e.read())
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                reason = getattr(e, "reason", e)
                code = "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason) else "network_error"
                raise TheStudentLifeError("Could not reach %s: %s" % (self.base_url, reason), code=code) from None
            retryable = status == 429 or (status >= 500 and safe)
            if retryable and attempt < self.max_retries:
                try:
                    wait = min(max(int(retry_after), 0), 30)
                except (TypeError, ValueError):
                    wait = min(0.5 * 2 ** attempt, 8)
                time.sleep(wait)
                attempt += 1
                continue
            err = parsed.get("error", {}) if isinstance(parsed, dict) else {}
            if not isinstance(err, dict):
                err = {}
            code = err.get("code") or (parsed.get("code") if isinstance(parsed, dict) else None)
            raise TheStudentLifeError(err.get("message") or code or "Request failed with status %d" % status, status=status, code=code, body=parsed)

    @staticmethod
    def _parse(raw: bytes) -> Any:
        text = raw.decode("utf-8", "replace") if raw else ""
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    # ---------- reads ----------
    def info(self) -> Dict[str, Any]:
        """Index of the API: endpoints, version and policies."""
        return self.request("/api/v1")

    def cities(self, q: Optional[str] = None, country: Optional[str] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Search the cities The Student Life covers."""
        return self.request("/api/v1/cities" + _query({"q": q, "country": country, "limit": limit, "cursor": cursor}))

    def city(self, slug: str) -> Dict[str, Any]:
        """Full student guide for one city (slug or name, e.g. "lisbon" or "Hong Kong")."""
        return self.request("/api/v1/cities/" + urllib.parse.quote(_slug(slug)))

    def events(self, city: Optional[str] = None, type: Optional[str] = None, upcoming: Optional[bool] = None, limit: Optional[int] = None, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Events with ticket prices and status. type: all, halloween, welcome_festival, semester_kickoff, orientation_week."""
        return self.request("/api/v1/events" + _query({"city": city, "type": type, "upcoming": upcoming, "limit": limit, "cursor": cursor}))

    def event(self, event_id: str) -> Dict[str, Any]:
        """One event by id, for example "berlin-hw26"."""
        return self.request("/api/v1/events/" + urllib.parse.quote(str(event_id).strip().lower()))

    def partners(self, category: Optional[str] = None, q: Optional[str] = None) -> Dict[str, Any]:
        """Student discount codes from partners."""
        return self.request("/api/v1/partners" + _query({"category": category, "q": q}))

    def pricing(self, city: Optional[str] = None) -> Dict[str, Any]:
        """What is free and what tickets cost, optionally for one city."""
        return self.request("/api/v1/pricing" + _query({"city": city}))

    def each_city(self, **params: Any) -> Iterator[Dict[str, Any]]:
        """Iterate every city across pages."""
        cursor = None
        while True:
            page = self.cities(cursor=cursor, **params)
            yield from page["cities"]
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def each_event(self, **params: Any) -> Iterator[Dict[str, Any]]:
        """Iterate every event across pages."""
        cursor = None
        while True:
            page = self.events(cursor=cursor, **params)
            yield from page["events"]
            cursor = page.get("next_cursor")
            if not cursor:
                return

    # ---------- async report jobs ----------
    def create_report(self, type: str, cities: Optional[List[str]] = None, event_type: Optional[str] = None) -> Dict[str, Any]:
        """Start a report job (202 Accepted). type: city_comparison (2 to 10 cities) or events_overview."""
        body: Dict[str, Any] = {"type": type}
        if cities is not None:
            body["cities"] = list(cities)
        if event_type is not None:
            body["event_type"] = event_type
        return self.request("/api/v1/reports", method="POST", body=body)

    def get_report(self, report_id: str) -> Dict[str, Any]:
        """Poll a report job."""
        return self.request("/api/v1/reports/" + urllib.parse.quote(str(report_id), safe=""))

    def run_report(self, type: str, cities: Optional[List[str]] = None, event_type: Optional[str] = None, timeout: float = 60.0) -> Dict[str, Any]:
        """Create a report and poll until it succeeds; returns the finished job (its result is in ["result"])."""
        job = self.create_report(type, cities, event_type)
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_report(job["id"])
            if job.get("status") == "succeeded":
                return job
            if time.monotonic() > deadline:
                raise TheStudentLifeError("Report did not finish in time", code="timeout", body=job)
            time.sleep(1)

    # ---------- write: reaches the real team inbox ----------
    def send_message(self, name: str, email: str, message: str, subject: Optional[str] = None, city: Optional[str] = None, dry_run: bool = False, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Email the team on someone's behalf. Only with their consent and their own name and email.

        dry_run=True validates and sends nothing. Pass an idempotency_key (a fresh
        UUID per message) to make retries safe.
        """
        body: Dict[str, Any] = {"name": name, "email": email, "message": message, "form_type": "agent-sdk"}
        if subject:
            body["subject"] = subject
        if city:
            body["city"] = city
        if dry_run:
            body["dry_run"] = True
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.request("/api/contact", method="POST", body=body, headers=headers)
