from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.social.models import PublicationTarget, SocialAccount

IG = SocialAccount.Platform.INSTAGRAM


def make_page(owner, external_id="1", name="Loja"):
    account = SocialAccount(owner=owner, platform=SocialAccount.Platform.FACEBOOK_PAGE, external_id=external_id, name=name)
    account.set_token("page-token")
    account.save()
    return account


def make_instagram(owner, page, external_id="17841", username="loja"):
    account = SocialAccount(
        owner=owner, platform=IG, external_id=external_id, name=username, username=username,
        parent=page, access_token_enc=page.access_token_enc,
    )
    account.save()
    return account


class InstagramModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def test_AC_22_instagram_is_a_platform_for_accounts_and_targets(self):
        self.assertIn("instagram", SocialAccount.Platform.values)
        self.assertIn("instagram", [c[0] for c in PublicationTarget._meta.get_field("platform").choices])

    def test_AC_2_instagram_account_shares_the_page_token_and_cascades(self):
        page = make_page(self.user)
        ig = make_instagram(self.user, page)
        self.assertEqual(ig.get_token(), "page-token")
        self.assertEqual(ig.parent, page)
        page.delete()
        self.assertFalse(SocialAccount.objects.filter(pk=ig.pk).exists())

    def test_AC_5_deleting_instagram_keeps_the_page(self):
        page = make_page(self.user)
        ig = make_instagram(self.user, page)
        ig.delete()
        self.assertTrue(SocialAccount.objects.filter(pk=page.pk).exists())
