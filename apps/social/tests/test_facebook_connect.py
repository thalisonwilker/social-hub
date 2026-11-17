import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.social.crypto import decrypt_token
from apps.social.models import SocialAccount
from apps.social.services import facebook_connect as fc
from apps.social.services.meta import GraphClient

from .helpers import PAGE_TOKEN_1, PAGES, USER_TOKEN, VALID_META_SETTINGS, graph_patches


@override_settings(**VALID_META_SETTINGS)
class FacebookConnectServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def fetch(self, pages=None):
        session = {}
        with graph_patches(pages):
            result = fc.fetch_pages(session, "code-1", GraphClient.from_settings())
        return session, result

    # ---- state -----------------------------------------------------------
    def test_AC_2_state_is_random_single_use_and_valid(self):
        session = {}
        state = fc.new_state(session)
        self.assertGreaterEqual(len(state), 32)
        self.assertTrue(fc.consume_state(session, state))
        self.assertFalse(fc.consume_state(session, state))  # reuso

    def test_AC_7_state_rejections(self):
        session = {}
        fc.new_state(session)
        self.assertFalse(fc.consume_state(session, "outro"))          # diferente
        self.assertFalse(fc.consume_state({}, "qualquer"))            # ausente
        self.assertFalse(fc.consume_state(session, ""))               # vazio
        session = {}
        state = fc.new_state(session)
        with mock.patch.object(fc.time, "time", return_value=10**12):  # expirado
            self.assertFalse(fc.consume_state(session, state))

    # ---- descoberta ------------------------------------------------------
    def test_AC_3_fetch_stores_encrypted_pages_and_creates_no_account(self):
        session, result = self.fetch()
        self.assertEqual((result.usable, result.skipped), (2, 0))
        self.assertEqual(SocialAccount.objects.count(), 0)
        pending = fc.pending_pages(session)
        self.assertEqual([p["id"] for p in pending], ["1", "2"])
        self.assertEqual(decrypt_token(pending[0]["token_enc"]), PAGE_TOKEN_1)

    def test_AC_16_session_never_holds_plaintext_tokens(self):
        session, _ = self.fetch()
        dump = json.dumps(session)
        self.assertNotIn(PAGE_TOKEN_1, dump)
        self.assertNotIn(USER_TOKEN, dump)

    def test_AC_9_no_pages_means_nothing_pending(self):
        session, result = self.fetch(pages=[])
        self.assertEqual((result.usable, result.skipped), (0, 0))
        self.assertIsNone(fc.pending_pages(session))

    def test_edge_page_without_token_is_skipped_and_flagged(self):
        sem_token = {**PAGES[0], "access_token": None}
        session, result = self.fetch(pages=[sem_token, PAGES[1]])
        self.assertEqual((result.usable, result.skipped), (1, 1))
        self.assertEqual([p["id"] for p in fc.pending_pages(session)], ["2"])

    def test_AC_10_pending_pages_expire(self):
        session, _ = self.fetch()
        with mock.patch.object(fc.time, "time", return_value=10**12):
            self.assertIsNone(fc.pending_pages(session))

    # ---- confirmação -----------------------------------------------------
    def test_AC_4_only_selected_pages_are_connected_and_session_cleared(self):
        session, _ = self.fetch()
        accounts = fc.save_selected(self.user, session, ["2"])
        self.assertEqual([a.external_id for a in accounts], ["2"])
        self.assertEqual(SocialAccount.objects.count(), 1)
        account = SocialAccount.objects.get()
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertNotIn("page-token", account.access_token_enc)
        self.assertEqual(account.get_token(), "page-token-TWO")
        self.assertIsNone(fc.pending_pages(session))

    def test_AC_4_multiple_pages_at_once(self):
        session, _ = self.fetch()
        fc.save_selected(self.user, session, ["1", "2", "2"])  # duplicata ignorada
        self.assertEqual(SocialAccount.objects.count(), 2)

    def test_AC_5_reconnect_updates_existing_without_duplicate(self):
        old = SocialAccount(owner=self.user, platform="facebook_page", external_id="1", name="Antigo",
                            status=SocialAccount.Status.NEEDS_REAUTH, last_error="190")
        old.set_token("velho")
        old.save()
        session, _ = self.fetch()
        fc.save_selected(self.user, session, ["1"])
        self.assertEqual(SocialAccount.objects.count(), 1)
        account = SocialAccount.objects.get()
        self.assertEqual(account.name, "Loja <b>Central</b>")
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertEqual(account.last_error, "")
        self.assertEqual(account.get_token(), PAGE_TOKEN_1)

    def test_AC_10_invalid_selections_create_nothing(self):
        session, _ = self.fetch()
        for ids, reason in (([], "empty"), (["999"], "unknown"), (["1", "999"], "unknown")):
            with self.subTest(ids=ids):
                with self.assertRaises(fc.SelectionError) as ctx:
                    fc.save_selected(self.user, session, ids)
                self.assertEqual(ctx.exception.reason, reason)
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertIsNotNone(fc.pending_pages(session))  # sessão segue válida p/ nova tentativa

    def test_AC_10_expired_or_missing_session_is_reported(self):
        with self.assertRaises(fc.SelectionError) as ctx:
            fc.save_selected(self.user, {}, ["1"])
        self.assertEqual(ctx.exception.reason, "expired")
