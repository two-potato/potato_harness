"""Explicit CI-only loopback HTTP smoke of the generated Django/Next.js MVP.

Only addresses http://127.0.0.1:3000; no external providers, PSP or real users.
A trusted CI step creates disposable accounts in the generated PostgreSQL app.
"""
from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:3000"
ORIGIN = BASE


class Browser:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.open = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self):
        for cookie in self.jar:
            if cookie.name == "csrftoken":
                return cookie.value
        raise AssertionError("No CSRF cookie from same-origin Next.js proxy")

    def call(self, path, *, data=None, expected=200, csrf=True, html=False):
        assert path.startswith("/") and not path.startswith("//") and ".." not in path
        headers = {"Accept": "text/html" if html else "application/json"}
        method = "GET" if data is None else "POST"
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            headers["Origin"] = ORIGIN
            if csrf:
                headers["X-CSRFToken"] = self.csrf()
            body = json.dumps(data).encode("utf-8")
        request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
        try:
            response = self.open.open(request, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status = response.status
            payload = response.read(1024 * 1024)
        assert status == expected, f"{method} {path}: expected {expected}, got {status}: {payload[:240]!r}"
        if html:
            assert b"<html" in payload.lower(), f"No HTML from {path}"
            return payload
        if expected >= 400:
            # Django's CSRF rejection is intentionally an HTML 403, while
            # DRF permission errors are JSON. The HTTP status is the invariant.
            return {"http_status": status}
        try:
            return json.loads(payload)
        except (UnicodeError, ValueError) as exc:
            raise AssertionError(f"Invalid JSON response from {path}") from exc


def wait_for_next():
    for attempt in range(70):
        try:
            return Browser().call("/api/auth/session/")
        except (OSError, AssertionError, urllib.error.URLError):
            time.sleep(1)
    raise AssertionError("Next.js loopback session proxy was unavailable after startup")


def main():
    wait_for_next()
    seller, reviewer, buyer = Browser(), Browser(), Browser()
    for browser, username, password in (
        (seller, "smoke_seller", "fixture-seller-01"),
        (reviewer, "smoke_moderator", "fixture-moderator-02"),
        (buyer, "smoke_buyer", "fixture-buyer-03"),
    ):
        info = browser.call("/api/auth/session/")
        assert info["authenticated"] is False
        # The plain Django login endpoint, unlike DRF anonymous auth,
        # is explicitly protected by Django's CSRF middleware.
        browser.call("/api/auth/login/",data={"username":username,"password":password},
                     expected=403,csrf=False)
        login = browser.call("/api/auth/login/",data={"username":username,"password":password})
        assert login["authenticated"]

    assert seller.call("/api/auth/session/")["seller"]
    assert reviewer.call("/api/auth/session/")["moderator"]
    assert not buyer.call("/api/auth/session/")["seller"]
    assert buyer.call("/api/listings/") == []
    buyer.call("/api/listings/",data={"slug":"forged","title":"Denied","price":"1.00","currency":"KZT"},expected=403)

    draft = seller.call("/api/listings/", data={"slug":"http-book","title":"HTTP Book",
                                                "description":"Reviewed locally","price":"29.50","currency":"KZT"},expected=201)
    assert draft["status"] == "DRAFT" and draft["content_revision"] == 1
    url = f"/api/listings/{draft['id']}/submit/"
    seller.call(url,data={"expected_revision":1})
    queued = reviewer.call("/api/moderation/queue/")
    assert [listing["id"] for listing in queued] == [draft["id"]]
    reviewer_decision = {"decision_id":str(uuid.uuid4()),"expected_revision":1,"verdict":"APPROVE","reason":""}
    decision_path=f"/api/moderation/{draft['id']}/decision/"
    seller.call(decision_path,data=reviewer_decision,expected=403)
    receipt = reviewer.call(decision_path,data=reviewer_decision)
    assert receipt["resulting_status"] == "PUBLISHED"
    assert receipt["content_revision"] == 1 and receipt["content_sha256"].startswith("sha256:")
    assert reviewer.call(decision_path,data=reviewer_decision) == receipt
    reviewer.call(decision_path,data={**reviewer_decision,"verdict":"REJECT"},expected=409)
    public=buyer.call("/api/listings/")
    assert len(public)==1 and public[0]["id"] == draft["id"]
    assert public[0]["title"] == "HTTP Book"
    storefront = buyer.call("/", html=True)
    assert b"HTTP Book" in storefront, "SSR storefront did not render approved listing"
    for page in ("/seller", "/moderation"):
        buyer.call(page,html=True)
    print("PASS: Next.js loopback sessions + CSRF + seller -> moderator -> public SSR buyer workflow")


if __name__ == "__main__":
    main()
