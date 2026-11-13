"""PostgreSQL-backed session, seller and human-moderation negative tests."""
import json
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from rest_framework.test import APIClient
from .models import Listing, ModerationDecision
from .moderation import content_digest


class ListingAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="seller_a", password="local-test-01")
        self.other = User.objects.create_user(username="seller_b", password="local-test-02")
        self.buyer = User.objects.create_user(username="buyer", password="local-test-03")
        self.moderator = User.objects.create_user(username="moderator", password="local-test-04", is_staff=True)
        self.not_staff = User.objects.create_user(username="moderator_not_staff", password="local-test-05")
        self.staff_no_group = User.objects.create_user(username="staff_no_group", password="local-test-06", is_staff=True)
        seller_group = Group.objects.get(name="seller")
        moderator_group = Group.objects.get(name="moderator")
        self.owner.groups.add(seller_group)
        self.other.groups.add(seller_group)
        self.moderator.groups.add(moderator_group)
        self.not_staff.groups.add(moderator_group)
        self.listing = Listing.objects.create(seller=self.owner, slug="book", title="Book", price="10.00")
        self.api = APIClient()

    def review_payload(self, *, revision=1, decision_id=None, verdict="APPROVE", reason=""):
        return {"expected_revision": revision, "decision_id": str(decision_id or uuid.uuid4()),
                "verdict": verdict, "reason": reason}

    def submit(self):
        self.api.force_authenticate(self.owner)
        response = self.api.post(f"/api/listings/{self.listing.pk}/submit/", {"expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.listing.refresh_from_db()

    def review(self, payload):
        self.api.force_authenticate(self.moderator)
        return self.api.post(f"/api/moderation/{self.listing.pk}/decision/", payload, format="json")

    def test_buyer_cannot_create_or_submit_listings(self):
        self.api.force_authenticate(self.buyer)
        body={"slug":"stolen", "title":"Not a seller", "price":"25.00", "currency":"KZT"}
        self.assertEqual(self.api.post("/api/listings/", body, format="json").status_code,403)
        self.assertEqual(self.api.post(f"/api/listings/{self.listing.pk}/submit/", {"expected_revision":1}, format="json").status_code,403)
        self.assertEqual(Listing.objects.count(),1)

    def test_seller_can_create_draft_but_never_self_publish(self):
        self.api.force_authenticate(self.owner)
        body={"slug":"new-book", "title":"Book 2", "price":"12.00", "currency":"KZT", "status":"PUBLISHED"}
        response=self.api.post("/api/listings/", body, format="json")
        self.assertEqual(response.status_code,201)
        new=Listing.objects.get(slug="new-book")
        self.assertEqual(new.seller,self.owner)
        self.assertEqual(new.status,Listing.Status.DRAFT)
        self.assertIsNone(new.approved_revision)

    def test_anonymous_cannot_see_draft(self):
        self.assertEqual(self.api.get("/api/listings/").data, [])
        self.assertEqual(self.api.get(f"/api/listings/{self.listing.pk}/").status_code, 404)

    def test_other_seller_cannot_view_or_edit_draft(self):
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(f"/api/listings/{self.listing.pk}/").status_code, 404)
        response = self.api.patch(f"/api/listings/{self.listing.pk}/", {"title": "stolen", "expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 404)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "Book")

    def test_seller_cannot_self_publish(self):
        self.api.force_authenticate(self.owner)
        response=self.api.patch(f"/api/listings/{self.listing.pk}/", {"status": "PUBLISHED", "title": "Updated", "expected_revision": 1}, format="json")
        self.assertEqual(response.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.DRAFT)
        self.assertIsNone(self.listing.approved_revision)
        self.assertEqual(self.listing.content_revision, 2)

    def test_stale_revision_and_submit(self):
        self.api.force_authenticate(self.owner)
        url=f"/api/listings/{self.listing.pk}/submit/"
        self.assertEqual(self.api.post(url, {"expected_revision": 2}, format="json").status_code, 400)
        self.assertEqual(self.api.post(url, {"expected_revision": 1}, format="json").status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.PENDING_REVIEW)
        self.assertEqual(self.listing.content_revision, 1)

    def test_published_fields_without_moderation_receipt_stay_private(self):
        self.listing.status=Listing.Status.PUBLISHED
        self.listing.approved_revision=0
        self.listing.save()
        self.assertEqual(len(self.api.get("/api/listings/").data), 0)
        self.listing.approved_revision=1
        self.listing.save()
        self.assertFalse(self.listing.is_visible)
        # Even matching status/revision fields do not bypass a missing APPROVE receipt.
        self.assertEqual(len(self.api.get("/api/listings/").data), 0)

    def test_private_seller_list_filters_other_accounts(self):
        self.api.force_authenticate(self.owner)
        own=self.api.get("/api/me/listings/")
        self.assertEqual(own.status_code,200)
        self.assertEqual([x["id"] for x in own.data], [str(self.listing.pk)])
        self.api.force_authenticate(self.other)
        self.assertEqual(list(self.api.get("/api/me/listings/").data), [])
        self.api.force_authenticate(self.buyer)
        self.assertEqual(self.api.get("/api/me/listings/").status_code,403)

    def test_moderator_review_queue_does_not_expose_drafts_to_others(self):
        self.submit()
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get("/api/moderation/queue/").status_code,403)
        self.api.force_authenticate(self.buyer)
        self.assertEqual(self.api.get("/api/moderation/queue/").status_code,403)
        self.api.force_authenticate(self.not_staff)
        self.assertEqual(self.api.get("/api/moderation/queue/").status_code,403)
        self.api.force_authenticate(self.staff_no_group)
        self.assertEqual(self.api.get("/api/moderation/queue/").status_code,403)
        self.api.force_authenticate(self.moderator)
        queue=self.api.get("/api/moderation/queue/")
        self.assertEqual(queue.status_code,200)
        self.assertEqual(len(queue.data),1)
        self.assertEqual(queue.data[0]["content_revision"],1)

    def test_human_approve_then_public_buyer_can_browse(self):
        self.submit()
        expected_digest=content_digest(self.listing)
        result=self.review(self.review_payload())
        self.assertEqual(result.status_code,200, result.data)
        self.assertEqual(result.data["content_sha256"],expected_digest)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status,Listing.Status.PUBLISHED)
        self.assertEqual(self.listing.approved_revision,1)
        self.assertEqual(ModerationDecision.objects.count(),1)
        self.api.force_authenticate(user=None)
        catalog=self.api.get("/api/listings/")
        self.assertEqual(catalog.status_code,200)
        self.assertEqual(len(catalog.data),1)
        self.assertEqual(catalog.data[0]["title"],"Book")

    def test_moderator_reject_and_seller_new_revision_restarts_review(self):
        self.submit()
        rejected=self.review(self.review_payload(verdict="REJECT",reason="Incomplete description"))
        self.assertEqual(rejected.status_code,200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status,Listing.Status.REJECTED)
        self.api.force_authenticate(user=None)
        self.assertEqual(len(self.api.get("/api/listings/").data),0)
        self.api.force_authenticate(self.owner)
        edited=self.api.patch(f"/api/listings/{self.listing.pk}/", {"title":"New title", "expected_revision":1}, format="json")
        self.assertEqual(edited.status_code,200)
        self.assertEqual(edited.data["content_revision"],2)
        self.assertEqual(self.api.post(f"/api/listings/{self.listing.pk}/submit/", {"expected_revision":2}, format="json").status_code,200)
        self.assertEqual(self.review(self.review_payload(revision=2)).status_code,200)
        self.assertEqual(ModerationDecision.objects.count(),2)

    def test_stale_decision_and_cross_role_submission_denied(self):
        self.submit()
        self.api.force_authenticate(self.owner)
        url=f"/api/moderation/{self.listing.pk}/decision/"
        self.assertEqual(self.api.post(url,self.review_payload(),format="json").status_code,403)
        self.assertEqual(self.review(self.review_payload(revision=2)).status_code,409)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status,Listing.Status.PENDING_REVIEW)
        self.assertEqual(ModerationDecision.objects.count(),0)

    def test_duplicate_decision_id_is_idempotent_but_substitution_denied(self):
        self.submit()
        decision_id=uuid.uuid4()
        payload=self.review_payload(decision_id=decision_id)
        self.assertEqual(self.review(payload).status_code,200)
        self.assertEqual(self.review(payload).status_code,200)
        self.assertEqual(self.review(dict(payload,verdict="REJECT")).status_code,409)
        self.assertEqual(self.review(self.review_payload()).status_code,409)
        self.assertEqual(ModerationDecision.objects.count(),1)

    def test_published_edit_revokes_visibility_before_re_review(self):
        self.submit()
        self.assertEqual(self.review(self.review_payload()).status_code,200)
        self.api.force_authenticate(self.owner)
        edited=self.api.patch(f"/api/listings/{self.listing.pk}/", {"title":"Edition 2", "expected_revision":1}, format="json")
        self.assertEqual(edited.status_code,200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status,Listing.Status.DRAFT)
        self.assertIsNone(self.listing.approved_revision)
        self.api.force_authenticate(user=None)
        self.assertEqual(len(self.api.get("/api/listings/").data),0)

    def test_csrf_protected_browser_login_and_logout(self):
        client=Client(enforce_csrf_checks=True)
        session=client.get("/api/auth/session/")
        self.assertEqual(session.status_code,200)
        self.assertFalse(session.json()["authenticated"])
        token=client.cookies["csrftoken"].value
        credentials=json.dumps({"username":"seller_a","password":"local-test-01"})
        self.assertEqual(client.post("/api/auth/login/",data=credentials,content_type="application/json").status_code,403)
        response=client.post("/api/auth/login/",data=credentials,content_type="application/json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200)
        state=client.get("/api/auth/session/").json()
        self.assertTrue(state["authenticated"])
        self.assertTrue(state["seller"])
        self.assertFalse(state["moderator"])
        self.assertEqual(client.get("/api/me/listings/").status_code,200)
        self.assertEqual(client.post("/api/auth/logout/",data="{}",content_type="application/json").status_code,403)
        new_token=client.cookies["csrftoken"].value
        self.assertEqual(client.post("/api/auth/logout/",data="{}",content_type="application/json",HTTP_X_CSRFTOKEN=new_token).status_code,200)
        self.assertFalse(client.get("/api/auth/session/").json()["authenticated"])

    def test_browser_moderation_post_requires_csrf_with_live_session(self):
        self.submit()
        browser=Client(enforce_csrf_checks=True)
        browser.force_login(self.moderator)
        browser.get("/api/auth/session/")
        url=f"/api/moderation/{self.listing.pk}/decision/"
        data=json.dumps(self.review_payload())
        self.assertEqual(browser.post(url,data=data,content_type="application/json").status_code,403)
        self.assertEqual(ModerationDecision.objects.count(),0)
        csrf=browser.cookies["csrftoken"].value
        self.assertEqual(browser.post(url,data=data,content_type="application/json",HTTP_X_CSRFTOKEN=csrf).status_code,200)
        self.assertEqual(ModerationDecision.objects.count(),1)

    def test_two_browser_sessions_complete_seller_to_buyer_flow(self):
        """PostgreSQL-backed E2E through real Django session+CSRF; no model or PSP."""
        seller=Client(enforce_csrf_checks=True)
        moderator=Client(enforce_csrf_checks=True)
        for client,username,password in ((seller,"seller_a","local-test-01"),
                                         (moderator,"moderator","local-test-04")):
            self.assertEqual(client.get("/api/auth/session/").status_code,200)
            reply=client.post("/api/auth/login/",data=json.dumps({"username":username,"password":password}),
                              content_type="application/json",
                              HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
            self.assertEqual(reply.status_code,200)

        def send(client,url,payload):
            return client.post(url,data=json.dumps(payload),content_type="application/json",
                               HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

        created=send(seller,"/api/listings/",{"slug":"example-new","title":"A reviewed book",
                                              "price":"49.99","currency":"KZT"})
        self.assertEqual(created.status_code,201,created.content)
        pk=created.json()["id"]
        sent=send(seller,f"/api/listings/{pk}/submit/",{"expected_revision":1})
        self.assertEqual(sent.status_code,200,sent.content)
        queue=moderator.get("/api/moderation/queue/")
        self.assertEqual(queue.status_code,200)
        self.assertEqual([x["id"] for x in queue.json()],[pk])
        receipt=send(moderator,f"/api/moderation/{pk}/decision/",self.review_payload())
        self.assertEqual(receipt.status_code,200,receipt.content)
        self.assertEqual(receipt.json()["resulting_status"],"PUBLISHED")
        buyer=Client(enforce_csrf_checks=True)
        public=buyer.get("/api/listings/")
        self.assertEqual(public.status_code,200)
        self.assertEqual([x["id"] for x in public.json()],[pk])
        self.assertEqual(public.json()[0]["title"],"A reviewed book")

    def test_bad_credentials_do_not_echo_password(self):
        client=Client(enforce_csrf_checks=True)
        client.get("/api/auth/session/")
        resp=client.post("/api/auth/login/",data=json.dumps({"username":"seller_a","password":"incorrect"}),
                         content_type="application/json",HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(resp.status_code,401)
        self.assertNotIn("incorrect",resp.content.decode())
