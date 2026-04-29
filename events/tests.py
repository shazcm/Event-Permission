from datetime import date
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Notification
from .hashtags import MAX_TAG_LENGTH, MAX_TAGS_PER_EVENT, parse_hashtags
from .models import Department, Event, Hashtag, Venue


User = get_user_model()


class HashtagParserTests(TestCase):
    def test_normalization_and_dedup(self):
        tags = parse_hashtags("#Technical technical #technical #Cultural")
        self.assertEqual(tags, ["technical", "cultural"])

    def test_invalid_tag_raises_error(self):
        with self.assertRaisesMessage(ValueError, "Invalid hashtag"):
            parse_hashtags("#tech-event")

    def test_limits_enforced(self):
        too_long = f"#{'a' * (MAX_TAG_LENGTH + 1)}"
        with self.assertRaisesMessage(ValueError, "too long"):
            parse_hashtags(too_long)

        many = " ".join(f"#t{i}" for i in range(MAX_TAGS_PER_EVENT + 1))
        with self.assertRaisesMessage(ValueError, "at most"):
            parse_hashtags(many)


class HashtagEventFlowTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Computer Science")
        self.venue = Venue.objects.create(name="Main Hall")
        self.faculty = User.objects.create_user(
            username="faculty1",
            password="pass1234",
            role="faculty",
            sub_role="hod",
            department=self.department,
        )
        self.principal = User.objects.create_user(
            username="principal1",
            password="pass1234",
            role="principal",
        )
        self.other_faculty = User.objects.create_user(
            username="faculty2",
            password="pass1234",
            role="faculty",
            sub_role="hod",
            department=self.department,
        )
        self.event = Event.objects.create(
            title="AI Workshop",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="1000.00",
            venue=self.venue,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
            description="Tech event",
            status="approved",
        )

    def test_faculty_owner_can_cancel_approved_event_directly(self):
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.post(
            reverse("faculty_request_cancel_event", args=[self.event.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "cancelled")
        self.assertFalse(self.event.is_cancellation_requested)
        self.assertTrue(
            Notification.objects.filter(
                event=self.event,
                type="cancel_requested",
                recipient=self.principal,
            ).exists()
        )

    def test_faculty_owner_can_cancel_pending_event_directly(self):
        self.event.status = "pending"
        self.event.save()
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.post(
            reverse("faculty_request_cancel_event", args=[self.event.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "cancelled")

    def test_faculty_cannot_cancel_other_users_event(self):
        self.client.login(username="faculty2", password="pass1234")
        response = self.client.post(
            reverse("faculty_request_cancel_event", args=[self.event.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "approved")

    def test_faculty_cannot_cancel_completed_event(self):
        self.event.status = "completed"
        self.event.save()
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.post(
            reverse("faculty_request_cancel_event", args=[self.event.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "completed")

    def test_principal_can_reject_approved_event(self):
        self.client.login(username="principal1", password="pass1234")
        response = self.client.post(
            reverse("principal_reject_approved_event", args=[self.event.id]),
            {"remark": "Policy issue"},
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "rejected")
        self.assertEqual(self.event.principal_remark, "Policy issue")
        self.assertTrue(
            Notification.objects.filter(
                event=self.event,
                type="rejected",
                recipient=self.faculty,
            ).exists()
        )

    def test_principal_reject_approved_event_requires_remark(self):
        self.client.login(username="principal1", password="pass1234")
        response = self.client.post(
            reverse("principal_reject_approved_event", args=[self.event.id]),
            {"remark": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "approved")

    def test_principal_reject_approved_event_blocked_for_completed(self):
        self.event.status = "completed"
        self.event.save()
        self.client.login(username="principal1", password="pass1234")
        response = self.client.post(
            reverse("principal_reject_approved_event", args=[self.event.id]),
            {"remark": "Too late"},
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "completed")

    def test_principal_reject_approved_event_blocked_for_verified(self):
        self.event.status = "verified"
        self.event.save()
        self.client.login(username="principal1", password="pass1234")
        response = self.client.post(
            reverse("principal_reject_approved_event", args=[self.event.id]),
            {"remark": "Too late"},
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "verified")

    def test_faculty_filter_supports_cancelled_status(self):
        self.event.status = "cancelled"
        self.event.save()
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.get(
            reverse("faculty_filter_events"),
            {"status": "cancelled"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")

    def test_download_report_shown_only_for_verified_event_detail(self):
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("event_detail", args=[self.event.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Download Detailed Report")

        self.event.status = "verified"
        self.event.save()
        response = self.client.get(reverse("event_detail", args=[self.event.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Download Detailed Report")

    def test_principal_approved_page_uses_modal_reject_not_inline_input(self):
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("principal_approved_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-reject-trigger")
        self.assertNotContains(response, 'placeholder="Reason for rejection"')

    def test_faculty_post_submission_due_shows_only_approved_owned(self):
        Event.objects.create(
            title="Declined Special Alpha",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="500.00",
            venue=self.venue,
            start_date=date(2026, 4, 2),
            end_date=date(2026, 4, 2),
            description="Rejected",
            status="rejected",
        )
        Event.objects.create(
            title="Other Faculty Approved",
            category="department",
            created_by=self.other_faculty,
            department=self.department,
            participation_type="mixed",
            budget="700.00",
            venue=self.venue,
            start_date=date(2026, 4, 3),
            end_date=date(2026, 4, 3),
            description="Other",
            status="approved",
        )
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.get(reverse("faculty_post_submission_due_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertNotContains(response, "Declined Special Alpha")
        self.assertNotContains(response, "Other Faculty Approved")

    def test_faculty_rejected_events_page_shows_only_rejected_owned(self):
        self.event.status = "rejected"
        self.event.principal_remark = "Try again"
        self.event.save()
        Event.objects.create(
            title="Published Demo Gamma",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="500.00",
            venue=self.venue,
            start_date=date(2026, 4, 4),
            end_date=date(2026, 4, 4),
            description="Approved",
            status="approved",
        )
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.get(reverse("faculty_rejected_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertNotContains(response, "Published Demo Gamma")
        self.assertContains(response, "Edit & Resubmit")

    def test_faculty_edit_resubmit_sets_event_back_to_pending(self):
        self.event.status = "rejected"
        self.event.principal_remark = "Needs changes"
        self.event.save()
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.post(
            reverse("faculty_edit_resubmit_event", args=[self.event.id]),
            {
                "title": "AI Workshop Updated",
                "start_date": "2026-04-01",
                "end_date": "2026-04-01",
                "start_time": "",
                "end_time": "",
                "chief_guest": "Guest",
                "venue": str(self.venue.id),
                "department": str(self.department.id),
                "participation_type": "mixed",
                "budget": "1000.00",
                "description": "Updated description",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "pending")
        self.assertEqual(self.event.principal_remark, "")
        self.assertEqual(self.event.title, "AI Workshop Updated")

    def test_faculty_edit_resubmit_blocked_for_non_rejected(self):
        self.client.login(username="faculty1", password="pass1234")
        response = self.client.get(reverse("faculty_edit_resubmit_event", args=[self.event.id]))
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "approved")

    def test_post_upload_saves_and_updates_hashtags(self):
        self.client.login(username="faculty1", password="pass1234")

        url = reverse("post_event_upload", args=[self.event.id])
        response = self.client.post(url, {"hashtags": "#Technical #Cultural"})
        self.assertEqual(response.status_code, 200)

        self.event.refresh_from_db()
        self.assertCountEqual(
            list(self.event.hashtags.values_list("name", flat=True)),
            ["technical", "cultural"],
        )

        response = self.client.post(
            url,
            {"hashtags": "#sports #Technical", "submit_report": "1", "report_text": "Done"},
        )
        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()
        self.assertCountEqual(
            list(self.event.hashtags.values_list("name", flat=True)),
            ["sports", "technical"],
        )

    def test_post_upload_invalid_hashtag_rejected(self):
        self.client.login(username="faculty1", password="pass1234")
        url = reverse("post_event_upload", args=[self.event.id])
        response = self.client.post(url, {"hashtags": "#bad-tag"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid hashtag")
        self.assertEqual(self.event.hashtags.count(), 0)

    def test_principal_view_all_filters_by_hashtag_legacy_param(self):
        self.event.status = "verified"
        self.event.save()
        tag = Hashtag.objects.create(name="technical")
        self.event.hashtags.add(tag)

        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("view_all_events"), {"hashtag": "technical"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")

        response = self.client.get(reverse("view_all_events"), {"hashtag": "cultural"})
        self.assertNotContains(response, "AI Workshop")

    def test_faculty_filter_by_hashtag_and_search(self):
        self.event.status = "completed"
        self.event.save()
        self.event.hashtags.add(Hashtag.objects.create(name="technical"))

        self.client.login(username="faculty1", password="pass1234")
        response = self.client.get(
            reverse("faculty_filter_events"),
            {"hashtag": "technical", "search": "AI", "status": "conducted"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")

    def test_principal_view_all_unified_search_with_hashtag_only(self):
        self.event.status = "verified"
        self.event.save()
        self.event.hashtags.add(Hashtag.objects.create(name="technical"))
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("view_all_events"), {"search": "#Technical"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertNotContains(response, 'name="hashtag"')
        self.assertContains(response, "Search events, hashtags (#tech), organizer...")
        self.assertNotContains(response, 'name="verified"')
        self.assertNotContains(response, 'type="submit">Search</button>')

    def test_principal_view_all_unified_search_text_and_hashtag(self):
        self.event.status = "verified"
        self.event.save()
        self.event.hashtags.add(Hashtag.objects.create(name="technical"))
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("view_all_events"), {"search": "Workshop #technical"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")

    def test_unified_search_hashtag_dedup_mixed_case(self):
        self.event.status = "verified"
        self.event.save()
        self.event.hashtags.add(Hashtag.objects.create(name="technical"))
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(
            reverse("view_all_events"),
            {"search": "#Technical #technical #TECHNICAL"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")

    def test_search_events_endpoint_supports_hashtag(self):
        self.event.hashtags.add(Hashtag.objects.create(name="technical"))
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("search_events"), {"q": "", "hashtag": "technical"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["title"], "AI Workshop")
        self.assertIn("technical", payload["events"][0]["hashtags"])

    def test_principal_quick_filter_upcoming(self):
        today = timezone.localdate()
        self.event.status = "verified"
        self.event.start_date = today + timedelta(days=1)
        self.event.end_date = today + timedelta(days=1)
        self.event.save()

        past_event = Event.objects.create(
            title="Past Event",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="900.00",
            venue=self.venue,
            start_date=today - timedelta(days=2),
            end_date=today - timedelta(days=2),
            description="Past",
            status="verified",
        )
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("view_all_events"), {"quick": "upcoming"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertNotContains(response, past_event.title)

    def test_principal_multi_category_csv_filter(self):
        self.event.status = "verified"
        self.event.save()
        other_event = Event.objects.create(
            title="Union Event",
            category="union",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="1000.00",
            venue=self.venue,
            start_date=date(2026, 4, 2),
            end_date=date(2026, 4, 2),
            description="Union",
            status="verified",
        )
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(
            reverse("view_all_events"),
            {"category": "department,union"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertContains(response, other_event.title)

    def test_quick_completed_ignores_legacy_verified_param(self):
        self.event.status = "completed"
        self.event.save()
        verified_event = Event.objects.create(
            title="Verified Event",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="1000.00",
            venue=self.venue,
            start_date=date(2026, 4, 3),
            end_date=date(2026, 4, 3),
            description="Verified",
            status="verified",
        )
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(
            reverse("view_all_events"),
            {"quick": "completed", "verified": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertNotContains(response, verified_event.title)

    def test_principal_all_quick_shows_all_statuses(self):
        self.event.status = "approved"
        self.event.save()
        completed_event = Event.objects.create(
            title="Completed Event",
            category="department",
            created_by=self.faculty,
            department=self.department,
            participation_type="mixed",
            budget="900.00",
            venue=self.venue,
            start_date=date(2026, 4, 5),
            end_date=date(2026, 4, 5),
            description="Completed",
            status="completed",
        )
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(reverse("view_all_events"), {"quick": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
        self.assertContains(response, completed_event.title)

    def test_principal_none_values_do_not_zero_results(self):
        self.event.status = "verified"
        self.event.save()
        self.client.login(username="principal1", password="pass1234")
        response = self.client.get(
            reverse("view_all_events"),
            {
                "quick": "all",
                "participation": "None",
                "start_date": "None",
                "end_date": "None",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Workshop")
