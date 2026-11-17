from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.social.models import SocialAccount

KEY = Fernet.generate_key().decode()


@override_settings(META_TOKEN_ENCRYPTION_KEY=KEY)
class SocialAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def make(self, owner, external_id="111", **kwargs):
        account = SocialAccount(
            owner=owner,
            platform=SocialAccount.Platform.FACEBOOK_PAGE,
            external_id=external_id,
            name=kwargs.pop("name", "Minha Página"),
            **kwargs,
        )
        account.set_token("EAAB-token-secreto")
        account.save()
        return account

    def test_AC_16_token_is_stored_encrypted_and_roundtrips(self):
        account = self.make(self.alice)
        account.refresh_from_db()
        self.assertNotIn("EAAB-token-secreto", account.access_token_enc)
        self.assertEqual(account.get_token(), "EAAB-token-secreto")

    def test_AC_16_str_and_repr_never_include_the_token(self):
        account = self.make(self.alice)
        for text in (str(account), repr(account)):
            self.assertNotIn("EAAB", text)
            self.assertNotIn(account.access_token_enc, text)

    def test_AC_5_unique_per_owner_platform_and_external_id(self):
        self.make(self.alice, "111")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(self.alice, "111")

    def test_AC_5_same_page_for_two_owners_is_allowed(self):
        self.make(self.alice, "111")
        self.make(self.bob, "111")
        self.assertEqual(SocialAccount.objects.filter(external_id="111").count(), 2)

    def test_AC_11_default_status_is_active_and_needs_reauth_flag(self):
        account = self.make(self.alice)
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertFalse(account.needs_reauth)
        account.status = SocialAccount.Status.NEEDS_REAUTH
        self.assertTrue(account.needs_reauth)

    def test_AC_14_accounts_are_scoped_by_owner(self):
        self.make(self.alice, "111")
        self.make(self.bob, "222")
        self.assertEqual(list(self.alice.social_accounts.values_list("external_id", flat=True)), ["111"])
