"""Trusted local moderation logic. No model, external PSP or publisher authority."""
import hashlib
import json


def content_digest(listing):
    """Digest the exact persisted listing content and its revision (no user PII)."""
    snapshot = {
        "listing_id": str(listing.pk),
        "seller_id": str(listing.seller_id),
        "slug": listing.slug,
        "title": listing.title,
        "description": listing.description,
        "price": format(listing.price, '.2f'),
        "currency": listing.currency,
        "content_revision": listing.content_revision,
    }
    encoded = json.dumps(snapshot, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return 'sha256:' + hashlib.sha256(encoded.encode('utf-8')).hexdigest()
