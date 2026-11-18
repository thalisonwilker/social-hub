from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .test_instagram_publisher import SETTINGS

S = PublicationTarget.Status


@override_settings(**SETTINGS, PUBLISH_MODE="worker")
class InstagramViewsTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page, username="loja")

    def test_AC_10_new_post_lists_the_instagram_account_and_enqueues_it(self):
        html = self.client.get(reverse("social:post_new")).content.decode()
        self.assertIn("Contas do Instagram", html)
        self.assertIn("@loja", html)
        response = self.client.post(
            reverse("social:post_new"), {"text": "Legenda #ig", "accounts": [self.ig.pk], "image": make_upload(size=(800, 800))}
        )
        publication = Publication.objects.get()
        self.assertRedirects(response, reverse("social:post_detail", args=[publication.pk]), fetch_redirect_response=False)
        target = publication.targets.get()
        self.assertEqual((target.platform, target.status), ("instagram", S.PENDING))

    def test_AC_6_new_post_without_image_is_rejected_and_creates_nothing(self):
        response = self.client.post(reverse("social:post_new"), {"text": "Legenda", "accounts": [self.ig.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O Instagram só publica com imagem")
        self.assertEqual(Publication.objects.count(), 0)

    def test_AC_19_reauth_instagram_is_shown_but_not_selectable(self):
        SocialAccount.objects.filter(pk=self.ig.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        fb = self.make_accounts(1)[0]
        html = self.client.get(reverse("social:post_new")).content.decode()
        self.assertIn("Reconexão necessária", html)
        self.assertIn("O Instagram “loja” precisa ser reconectado", html)
        self.assertIsNotNone(fb)

    def test_AC_18_detail_shows_instagram_target_link_and_uncertain_actions(self):
        publication = publishing.create_publication(self.alice, "Legenda", sanitize_image(make_upload()), [self.ig])
        PublicationTarget.objects.filter(publication=publication).update(
            status=S.PUBLISHED, permalink="https://www.instagram.com/p/ABC/", external_post_id="m-1"
        )
        html = self.client.get(reverse("social:post_detail", args=[publication.pk])).content.decode()
        self.assertIn("instagram", html.lower())
        self.assertIn("https://www.instagram.com/p/ABC/", html)
        PublicationTarget.objects.filter(publication=publication).update(status=S.UNCERTAIN, permalink="")
        html = self.client.get(reverse("social:post_detail", args=[publication.pk])).content.decode()
        self.assertIn("Já foi publicado", html)
        self.assertIn("Reenviar", html)
