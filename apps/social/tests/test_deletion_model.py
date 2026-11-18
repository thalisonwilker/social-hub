from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.social.models import PublicationTarget
from apps.social.services.threads import SCOPES

from .publication_helpers import PublicationTestMixin


class DeletionModelTests(PublicationTestMixin, TestCase):
    def test_AC_13_deleted_at_defaults_to_null_and_keeps_the_status(self):
        pub = self.make_publication()
        target = pub.targets.first()
        self.assertIsNone(target.deleted_at)
        self.assertFalse(target.is_deleted)
        PublicationTarget.objects.filter(pk=target.pk).update(status="published", deleted_at=timezone.now())
        target.refresh_from_db()
        self.assertTrue(target.is_deleted)
        self.assertEqual(target.status, "published")


class ThreadsScopeTests(SimpleTestCase):
    def test_AC_14_login_scope_includes_threads_delete(self):
        self.assertEqual(SCOPES.split(","), ["threads_basic", "threads_content_publish", "threads_delete"])
