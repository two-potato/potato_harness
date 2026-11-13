"""Run with PostgreSQL and DJANGO_SECRET_KEY set in an isolated test runner."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Listing


class ListingAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="seller_a", password="local-test-01")
        self.other = User.objects.create_user(username="seller_b", password="local-test-02")
        self.buyer = User.objects.create_user(username="buyer", password="local-test-03")
        seller_group = Group.objects.create(name="seller")
        self.owner.groups.add(seller_group)
        self.other.groups.add(seller_group)
        self.listing = Listing.objects.create(seller=self.owner, slug="book", title="Book", price="10.00")
        self.api = APIClient()

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

    def test_published_requires_exact_approved_revision(self):
        self.listing.status=Listing.Status.PUBLISHED
        self.listing.approved_revision=0
        self.listing.save()
        self.assertEqual(len(self.api.get("/api/listings/").data), 0)
        self.listing.approved_revision=1
        self.listing.save()
        self.assertEqual(len(self.api.get("/api/listings/").data), 1)
