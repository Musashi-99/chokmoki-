"""F-10 mass-assignment hardening tests."""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.blog_post import BlogPostUpdate
from src.models.testimonial import TestimonialUpdate
from src.security.mass_assignment import PROTECTED_UPDATE_FIELDS, build_update_payload, require_update_fields


class TestMassAssignmentHelpers:
    def test_strips_protected_fields(self):
        data = build_update_payload(
            TestimonialUpdate,
            {
                "name": "Alice",
                "_id": "evil",
                "created_at": "2020-01-01T00:00:00",
            },
        )
        assert data == {"name": "Alice"}
        for field in PROTECTED_UPDATE_FIELDS:
            assert field not in data

    def test_rejects_unknown_fields(self):
        with pytest.raises(ValueError, match="Invalid request parameters"):
            build_update_payload(TestimonialUpdate, {"hacker_field": True})

    def test_require_update_fields_raises_on_empty(self):
        with pytest.raises(ValueError, match="No valid fields"):
            require_update_fields({})

    def test_partial_blog_update_allows_single_field(self):
        data = build_update_payload(BlogPostUpdate, {"title": "Updated"})
        assert data == {"title": "Updated"}

    def test_rating_bounds_enforced(self):
        with pytest.raises(ValueError):
            build_update_payload(TestimonialUpdate, {"rating": 99})
