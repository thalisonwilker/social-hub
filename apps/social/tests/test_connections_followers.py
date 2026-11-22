"""Spec 0017, AC-9 — seguidores lidos ao "Atualizar informações" (cliente Graph + view de verificação)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount
from apps.social.services.evolution import EvolutionClient
from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.services.threads import ThreadsClient

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .helpers import VALID_META_SETTINGS
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.ok = payload, status, status < 400

    def json(self):
        return self.payload


class GraphFollowersContractTests(SimpleTestCase):
    def client_with(self, payload, status=200):
        session = mock.Mock()
        session.request.return_value = FakeResponse(payload, status)
        return GraphClient(app_id="1", app_secret="s", config_id="c", redirect_uri="https://x/", version="v27.0", session=session), session

    def test_AC_9_reads_followers_count_with_token_in_header(self):
        client, session = self.client_with({"followers_count": 1234, "id": "1"})
        self.assertEqual(client.get_followers_count("1", "tok"), 1234)
        call = session.request.call_args
        self.assertTrue(call.args[1].endswith("/v27.0/1"))
        self.assertEqual(call.kwargs["params"], {"fields": "followers_count"})
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_AC_9_missing_or_invalid_value_is_none(self):
        for payload in ({}, {"followers_count": "x"}, {"followers_count": -1}, {"followers_count": True}):
            client, _ = self.client_with(payload)
            self.assertIsNone(client.get_followers_count("1", "tok"), payload)

    def test_AC_9_api_error_raises_sanitized(self):
        client, _ = self.client_with({"error": {"code": 190, "message": "x"}}, status=400)
        with self.assertRaises(MetaApiError) as ctx:
            client.get_followers_count("1", "tok")
        self.assertTrue(ctx.exception.is_token_error)


@override_settings(**{**VALID_META_SETTINGS, **THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class CheckUpdatesFollowersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def check(self, account):
        return self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)

    def test_AC_9_facebook_ok_saves_followers_and_last_checked(self):
        page = make_page(self.user)
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}), \
             mock.patch.object(GraphClient, "get_followers_count", return_value=4321) as followers:
            response = self.check(page)
        followers.assert_called_once_with("1", "page-token")
        page.refresh_from_db()
        self.assertEqual(page.followers_count, 4321)
        self.assertIsNotNone(page.last_checked_at)
        self.assertContains(response, "4.321")

    def test_AC_9_instagram_reads_its_own_id_with_the_page_token(self):
        page = make_page(self.user)
        ig = make_instagram(self.user, page)
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}), \
             mock.patch.object(GraphClient, "get_followers_count", return_value=88) as followers:
            self.check(ig)
        followers.assert_called_once_with("17841", "page-token")
        ig.refresh_from_db()
        self.assertEqual(ig.followers_count, 88)

    def test_AC_9_followers_failure_keeps_previous_value_and_status(self):
        page = make_page(self.user)
        SocialAccount.objects.filter(pk=page.pk).update(followers_count=50)
        for error in (MetaApiError("x", code=1), MetaApiError("x", code=190)):
            with self.subTest(code=error.code), \
                 mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}), \
                 mock.patch.object(GraphClient, "get_followers_count", side_effect=error):
                response = self.check(page)
            page.refresh_from_db()
            self.assertEqual(page.followers_count, 50)
            self.assertEqual(page.status, SocialAccount.Status.ACTIVE)
            self.assertIsNotNone(page.last_checked_at)
            self.assertContains(response, "conectada e funcionando")

    def test_AC_9_none_from_api_keeps_previous_value(self):
        page = make_page(self.user)
        SocialAccount.objects.filter(pk=page.pk).update(followers_count=50)
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}), \
             mock.patch.object(GraphClient, "get_followers_count", return_value=None):
            self.check(page)
        page.refresh_from_db()
        self.assertEqual(page.followers_count, 50)

    def test_AC_9_failed_check_does_not_read_followers(self):
        page = make_page(self.user)
        with mock.patch.object(GraphClient, "get_page", side_effect=MetaApiError("x", code=190)), \
             mock.patch.object(GraphClient, "get_followers_count") as followers:
            self.check(page)
        followers.assert_not_called()

    def test_AC_9_threads_and_whatsapp_do_not_read_followers(self):
        threads = SocialAccount(owner=self.user, platform="threads", external_id="900", name="Maria", username="maria")
        threads.set_token("t")
        threads.save()
        wa = make_whatsapp_account(self.user)
        with mock.patch.object(GraphClient, "get_followers_count") as followers, \
             mock.patch.object(ThreadsClient, "get_profile", return_value={"id": "900"}), \
             mock.patch.object(EvolutionClient, "connection_state", return_value="open"):
            self.check(threads)
            response = self.check(wa)
        followers.assert_not_called()
        for account in (threads, wa):
            account.refresh_from_db()
            self.assertIsNone(account.followers_count)
        self.assertContains(response, "conectada e funcionando")
