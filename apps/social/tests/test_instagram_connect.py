from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.social.crypto import decrypt_token
from apps.social.models import SocialAccount
from apps.social.services import facebook_connect as fc
from apps.social.services.meta import GraphClient

from .helpers import PAGE_TOKEN_1, PAGES, VALID_META_SETTINGS, graph_patches

IG = SocialAccount.Platform.INSTAGRAM
INSTAGRAM = {"id": "17841400", "username": "lojacentral", "name": "Loja Central", "picture_url": "https://img/ig.jpg"}


def pages_with(instagram):
    pages = [dict(p) for p in PAGES]
    pages[0]["instagram"] = instagram
    return pages


@override_settings(**VALID_META_SETTINGS)
class InstagramConnectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def fetch(self, pages):
        session = {}
        with graph_patches(pages):
            fc.fetch_pages(session, "code-1", GraphClient.from_settings())
        return session

    def connect(self, instagram, ids=("1",)):
        session = self.fetch(pages_with(instagram))
        fc.save_selected(self.user, session, list(ids))
        return session

    def test_AC_1_list_pages_asks_for_instagram_and_summarizes_it(self):
        captured = {}

        def fake_request(self, method, path, **kwargs):
            captured["fields"] = kwargs["params"]["fields"]
            return {"data": [
                {"id": "1", "name": "A", "access_token": "t", "instagram_business_account": {
                    "id": 99, "username": "ig", "profile_picture_url": "https://img"}},
                {"id": "2", "name": "B", "access_token": "t2"},
            ]}

        with mock.patch.object(GraphClient, "_request", fake_request):
            pages = GraphClient.from_settings().list_pages("user-token")
        self.assertIn("instagram_business_account{id,username,name,profile_picture_url}", captured["fields"])
        self.assertEqual(pages[0]["instagram"]["id"], "99")
        self.assertEqual(pages[0]["instagram"]["username"], "ig")
        self.assertIsNone(pages[1]["instagram"])

    def test_AC_1_session_keeps_instagram_summary_without_extra_token(self):
        session = self.fetch(pages_with(INSTAGRAM))
        entry = fc.pending_pages(session)[0]
        self.assertEqual(entry["instagram"], INSTAGRAM)
        self.assertNotIn(PAGE_TOKEN_1, str(session))  # só token cifrado
        self.assertNotIn("token", str(entry["instagram"]))

    def test_AC_2_creates_instagram_account_with_the_page_token(self):
        self.connect(INSTAGRAM)
        page = SocialAccount.objects.get(platform=SocialAccount.Platform.FACEBOOK_PAGE, external_id="1")
        ig = SocialAccount.objects.get(platform=IG)
        self.assertEqual((ig.owner, ig.external_id, ig.username, ig.parent), (self.user, "17841400", "lojacentral", page))
        self.assertEqual(ig.status, SocialAccount.Status.ACTIVE)
        self.assertEqual(decrypt_token(ig.access_token_enc), PAGE_TOKEN_1)
        self.assertNotEqual(ig.access_token_enc, PAGE_TOKEN_1)

    def test_AC_2_does_not_duplicate_on_second_connection(self):
        self.connect(INSTAGRAM)
        self.connect({**INSTAGRAM, "username": "novo"})
        self.assertEqual(SocialAccount.objects.filter(platform=IG).count(), 1)
        self.assertEqual(SocialAccount.objects.get(platform=IG).username, "novo")

    def test_AC_3_page_without_instagram_creates_nothing(self):
        self.connect(None)
        self.assertFalse(SocialAccount.objects.filter(platform=IG).exists())
        self.assertEqual(SocialAccount.objects.filter(platform=SocialAccount.Platform.FACEBOOK_PAGE).count(), 1)

    def test_AC_4_reconnection_refreshes_token_and_status(self):
        self.connect(INSTAGRAM)
        SocialAccount.objects.filter(platform=IG).update(status=SocialAccount.Status.NEEDS_REAUTH, last_error="x")
        self.connect(INSTAGRAM)
        ig = SocialAccount.objects.get(platform=IG)
        self.assertEqual(ig.status, SocialAccount.Status.ACTIVE)
        self.assertEqual(ig.last_error, "")

    def test_AC_4_removes_instagram_when_the_link_is_gone(self):
        self.connect(INSTAGRAM)
        self.connect(None)
        self.assertFalse(SocialAccount.objects.filter(platform=IG).exists())

    def test_AC_4_replaces_instagram_when_the_page_links_another(self):
        self.connect(INSTAGRAM)
        self.connect({**INSTAGRAM, "id": "555"})
        self.assertEqual(list(SocialAccount.objects.filter(platform=IG).values_list("external_id", flat=True)), ["555"])

    def test_AC_21_only_the_selected_page_gets_an_instagram_account(self):
        pages = pages_with(INSTAGRAM)
        pages[1]["instagram"] = {**INSTAGRAM, "id": "777"}
        session = self.fetch(pages)
        fc.save_selected(self.user, session, ["1"])
        self.assertEqual(list(SocialAccount.objects.filter(platform=IG).values_list("external_id", flat=True)), ["17841400"])
