from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.models import PublicationTarget

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class DeletionUiTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.fb = self.make_accounts(1)[0]
        self.th = make_threads_account(self.alice, "900")
        self.ig = make_instagram(self.alice, make_page(self.alice, "50"))
        self.wa = make_whatsapp_account(self.alice, "loja", key="k")
        self.pub = self.make_publication([self.fb, self.th, self.ig, self.wa])
        self.pub.targets.update(status=S.PUBLISHED, external_post_id="PID", permalink="https://x/p")

    def detail(self):
        return self.client.get(reverse("social:post_detail", args=[self.pub.pk])).content.decode()

    def test_AC_4_actions_are_posts_with_confirmation_and_say_what_happens(self):
        html = self.detail()
        self.assertIn(reverse("social:post_remove", args=[self.pub.pk]), html)
        self.assertIn("Os posts já publicados continuam nas redes sociais", html)
        self.assertIn("Esta ação é irreversível", html)
        self.assertIn("O post continua na rede social.", html)
        import re

        forms = re.findall(r'<form method="post" action="[^"]*/(?:apagar|remover)/"[^>]*>', html)
        self.assertEqual(len(forms), 1 + 1 + 2 + 4)  # publicação: apagar+remover; destinos: 2 apagar + 4 remover
        self.assertTrue(all("data-confirm=" in f for f in forms))

    def test_AC_4_uncertain_target_warns_it_may_be_published(self):
        self.pub.targets.filter(platform="instagram").update(status=S.UNCERTAIN, external_post_id="")
        html = self.detail()
        self.assertIn("Este destino está Incerto: o post pode estar publicado na rede.", html)
        self.assertIn("há destino Incerto", html)

    def test_AC_7_unsupported_platforms_have_no_delete_button_but_the_hint(self):
        html = self.detail()
        for platform in ("instagram", "whatsapp_status"):
            target = self.pub.targets.get(platform=platform)
            self.assertNotIn(reverse("social:target_delete_remote", args=[self.pub.pk, target.pk]), html)
        self.assertEqual(html.count("apague pelo app"), 2)
        for platform in ("facebook_page", "threads"):
            target = self.pub.targets.get(platform=platform)
            self.assertIn(reverse("social:target_delete_remote", args=[self.pub.pk, target.pk]), html)

    def test_AC_13_deleted_target_shows_the_state_without_the_link_and_status_is_unchanged(self):
        self.pub.targets.filter(platform="facebook_page").update(deleted_at=timezone.now())
        html = self.detail()
        self.assertIn("Apagado na plataforma", html)
        self.assertEqual(html.count('href="https://x/p"'), 3)  # os outros 3 destinos seguem com link
        self.assertEqual(self.pub.status, "published")
        target = self.pub.targets.get(platform="facebook_page")
        self.assertNotIn(reverse("social:target_delete_remote", args=[self.pub.pk, target.pk]), html)

    def test_AC_8_reauth_and_disconnected_accounts_hint_instead_of_a_button(self):
        from apps.social.models import SocialAccount

        SocialAccount.objects.filter(pk=self.fb.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        self.pub.targets.filter(platform="threads").update(account=None)
        html = self.detail()
        self.assertIn("reconecte a conta para apagar", html)
        self.assertIn("conta desconectada: apague pelo app", html)

    def test_AC_4_list_has_remove_from_hub_with_confirmation(self):
        html = self.client.get(reverse("social:posts")).content.decode()
        self.assertIn(reverse("social:post_remove", args=[self.pub.pk]), html)
        self.assertIn("Os posts já publicados continuam nas redes sociais", html)

    def test_AC_8_no_bulk_button_when_nothing_is_deletable(self):
        self.pub.targets.filter(platform__in=["facebook_page", "threads"]).update(deleted_at=timezone.now())
        html = self.detail()
        self.assertNotIn(reverse("social:post_delete_remote", args=[self.pub.pk]), html)
