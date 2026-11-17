import shutil
import tempfile
from datetime import timedelta

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.models import Publication, PublicationTarget, SocialAccount

KEY = Fernet.generate_key().decode()
NOW = timezone.now()


@override_settings(META_TOKEN_ENCRYPTION_KEY=KEY)
class ThreadsAccountModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def account(self, owner=None, external_id="900", **kwargs):
        acc = SocialAccount(owner=owner or self.alice, platform=SocialAccount.Platform.THREADS,
                            external_id=external_id, name="Maria", username="maria", **kwargs)
        acc.set_token("threads-long-token")
        acc.save()
        return acc

    def test_AC_4_threads_account_stores_username_token_and_validity(self):
        """AC-4: conta threads guarda @usuário, token cifrado, expiração e data da última renovação."""
        acc = self.account(token_expires_at=NOW + timedelta(days=60), token_refreshed_at=NOW)
        acc.refresh_from_db()
        self.assertEqual((acc.platform, acc.username), ("threads", "maria"))
        self.assertNotIn("threads-long-token", acc.access_token_enc)
        self.assertEqual(acc.get_token(), "threads-long-token")
        self.assertEqual(acc.get_platform_display(), "Perfil do Threads")

    def test_AC_5_unique_per_owner_platform_and_external_id(self):
        """AC-5: mesmo perfil do mesmo dono não duplica; outro dono pode ter o mesmo perfil."""
        self.account(external_id="900")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.account(external_id="900")
        self.account(owner=self.bob, external_id="900")
        facebook = SocialAccount(owner=self.alice, platform="facebook_page", external_id="900", name="Pág")
        facebook.set_token("t")
        facebook.save()  # mesma ID em outra plataforma é permitido
        self.assertEqual(SocialAccount.objects.filter(external_id="900").count(), 3)

    def test_AC_9_token_expiry_helpers(self):
        """AC-9: token_expired e days_until_token_expiry (None para quem não expira)."""
        acc = self.account(token_expires_at=NOW + timedelta(days=10, hours=5))
        self.assertFalse(acc.token_expired(NOW))
        self.assertEqual(acc.days_until_token_expiry(NOW), 10)
        self.assertTrue(acc.token_expired(NOW + timedelta(days=11)))
        self.assertEqual(acc.days_until_token_expiry(NOW + timedelta(days=30)), 0)
        self.assertTrue(acc.token_expired(acc.token_expires_at))  # no instante exato já expirou

    def test_AC_9_facebook_pages_never_expire(self):
        """AC-9: sem validade (campos nulos) o token não expira e não há contagem de dias."""
        page = SocialAccount(owner=self.alice, platform="facebook_page", external_id="1", name="Pág")
        page.set_token("t")
        page.save()
        self.assertIsNone(page.token_expires_at)
        self.assertFalse(page.token_expired(NOW + timedelta(days=9999)))
        self.assertIsNone(page.days_until_token_expiry(NOW))


@override_settings(META_TOKEN_ENCRYPTION_KEY=KEY)
class ThreadsPublicationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        # Nunca grava no MEDIA_ROOT real.
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def test_AC_23_publication_without_image_is_allowed(self):
        """AC-23: publicação só do Threads não tem imagem; has_image reflete isso."""
        pub = Publication.objects.create(owner=self.alice, text="Só texto")
        self.assertFalse(pub.has_image)
        self.assertEqual((pub.image.name, pub.image_content_type), ("", ""))
        with_image = Publication(owner=self.alice, text="x", image_content_type="image/jpeg")
        with_image.image.save("a.jpg", ContentFile(b"x"), save=False)
        with_image.save()
        self.assertTrue(with_image.has_image)

    def test_AC_21_target_snapshots_platform_and_container_id(self):
        """AC-21: o alvo guarda a plataforma (snapshot) e o id do container do Threads."""
        pub = Publication.objects.create(owner=self.alice, text="x")
        default = PublicationTarget.objects.create(publication=pub, page_external_id="1", page_name="Pág")
        threads = PublicationTarget.objects.create(
            publication=pub, page_external_id="9", page_name="@maria", platform="threads", external_container_id="c1")
        self.assertEqual(default.platform, "facebook_page")  # padrão preserva o comportamento da 0003
        self.assertEqual((threads.platform, threads.external_container_id), ("threads", "c1"))
        self.assertEqual(default.external_container_id, "")
