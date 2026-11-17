from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.social.models import Publication, PublicationTarget, SocialAccount

from .helpers import KEY


@override_settings(META_TOKEN_ENCRYPTION_KEY=KEY)
class PublicationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def publication(self, owner=None, text="Olá"):
        pub = Publication(owner=owner or self.alice, text=text, image_content_type="image/jpeg")
        pub.image.save("x.jpg", ContentFile(b"fake"), save=False)
        pub.save()
        return pub

    def account(self, external_id="1"):
        acc = SocialAccount(owner=self.alice, platform="facebook_page", external_id=external_id, name=f"P{external_id}")
        acc.set_token("t")
        acc.save()
        return acc

    def target(self, pub, ext="1", status=PublicationTarget.Status.PENDING, account=True, **kwargs):
        return PublicationTarget.objects.create(
            publication=pub, account=self.account(ext) if account is True else account,
            page_external_id=ext, page_name=f"Página {ext}", status=status, **kwargs)

    def test_AC_15_overall_status_is_derived_from_targets(self):
        S = PublicationTarget.Status
        pub = self.publication()
        self.assertEqual(pub.status, Publication.Status.PENDING)  # sem alvos
        self.target(pub, "1", S.PUBLISHED)
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)
        self.target(pub, "2", S.PENDING)
        self.assertEqual(pub.status, Publication.Status.PENDING)
        self.target(pub, "3", S.SENDING)
        self.assertEqual(pub.status, Publication.Status.PENDING)
        self.target(pub, "4", S.FAILED)
        self.assertEqual(pub.status, Publication.Status.FAILED)
        self.assertEqual(pub.status_label, "Com falhas")
        self.assertEqual(pub.status_counts(), {"pending": 1, "sending": 1, "published": 1, "failed": 1})

    def test_AC_15_all_published_is_published(self):
        pub = self.publication()
        for i in "12":
            self.target(pub, i, PublicationTarget.Status.PUBLISHED)
        self.assertEqual(pub.status_label, "Publicada")

    def test_AC_12_retryable_targets(self):
        S = PublicationTarget.Status
        pub = self.publication()
        self.target(pub, "1", S.PUBLISHED)
        self.assertFalse(pub.has_retryable_targets)
        self.target(pub, "2", S.FAILED)
        self.assertTrue(pub.has_retryable_targets)

    def test_AC_14_failed_target_without_account_is_not_retryable(self):
        pub = self.publication()
        t = self.target(pub, "1", PublicationTarget.Status.FAILED, account=None)
        self.assertFalse(t.is_retryable)

    def test_AC_14_snapshot_survives_account_disconnection(self):
        pub = self.publication()
        t = self.target(pub, "1")
        t.account.delete()
        t.refresh_from_db()
        self.assertIsNone(t.account)
        self.assertEqual((t.page_external_id, t.page_name), ("1", "Página 1"))

    def test_AC_3_one_target_per_page_in_a_publication(self):
        pub = self.publication()
        self.target(pub, "1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PublicationTarget.objects.create(publication=pub, page_external_id="1", page_name="dup")
        other = self.publication()
        self.target(other, "1", account=None)  # mesma Página em outra publicação: ok

    def test_AC_18_publications_are_scoped_by_owner(self):
        self.publication(self.alice)
        self.publication(self.bob)
        self.assertEqual(self.alice.publications.count(), 1)

    def test_str_never_includes_text(self):
        self.assertNotIn("segredo", str(self.publication(text="segredo do texto")))
        self.assertEqual(self.publication().image.name.startswith("publications/"), True)
