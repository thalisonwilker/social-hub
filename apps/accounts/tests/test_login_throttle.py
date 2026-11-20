import uuid
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts import login_throttle as lt
from apps.accounts.models import LoginAttempt


class PureHelpersTests(SimpleTestCase):
    def test_hash_email_is_stable_and_not_the_email(self):
        h = lt.hash_email("a@b.com")
        self.assertEqual(h, lt.hash_email("a@b.com"))
        self.assertNotEqual(h, lt.hash_email("c@b.com"))
        self.assertEqual(len(h), 64)
        self.assertNotIn("a@b.com", h)

    def test_parse_key_accepts_only_canonical_uuid(self):
        good = str(uuid.uuid4())
        self.assertEqual(str(lt.parse_key(good)), good)
        for bad in (None, "", "abc", good.replace("-", ""), "{" + good + "}", good + "x", "' OR 1=1 --" + "x" * 25):
            self.assertIsNone(lt.parse_key(bad), bad)


class RetryAfterTests(TestCase):
    def add(self, succeeded=False, minutes_ago=0, email="a@b.com", ip="10.0.0.1"):
        attempt = LoginAttempt.objects.create(
            key=uuid.uuid4(), email_hash=lt.hash_email(email), ip=ip, succeeded=succeeded
        )
        LoginAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))

    def test_AC_5_five_failures_per_email_block(self):
        for m in (10, 8, 6, 4):
            self.add(minutes_ago=m)
        self.assertIsNone(lt.retry_after(lt.hash_email("a@b.com"), "10.0.0.9"))
        self.add(minutes_ago=2)
        wait = lt.retry_after(lt.hash_email("a@b.com"), "10.0.0.9")
        self.assertTrue(4 * 60 < wait <= 5 * 60, wait)  # a falha de 10 min atrás sai em ~5 min

    def test_AC_5_failures_outside_window_do_not_count(self):
        for m in (40, 30, 20, 16, 1):
            self.add(minutes_ago=m)
        self.assertIsNone(lt.retry_after(lt.hash_email("a@b.com"), "10.0.0.9"))

    def test_AC_5_success_resets_email_count(self):
        for m in (10, 9, 8, 7):
            self.add(minutes_ago=m)
        self.add(succeeded=True, minutes_ago=6)
        self.add(minutes_ago=1)
        self.assertIsNone(lt.retry_after(lt.hash_email("a@b.com"), "10.0.0.9"))

    def test_AC_5_twenty_failures_per_ip_block_any_email(self):
        for i in range(20):
            self.add(email=f"u{i}@x.com", minutes_ago=1)
        self.assertIsNotNone(lt.retry_after(lt.hash_email("novo@x.com"), "10.0.0.1"))
        self.assertIsNone(lt.retry_after(lt.hash_email("novo@x.com"), "10.0.0.2"))

    def test_AC_10_purge_removes_older_than_24h(self):
        self.add(minutes_ago=24 * 60 + 1)
        self.add(minutes_ago=60)
        lt.purge_old()
        self.assertEqual(LoginAttempt.objects.count(), 1)
