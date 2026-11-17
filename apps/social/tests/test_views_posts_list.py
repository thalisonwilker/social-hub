from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.social.models import Publication

from .publication_helpers import PublicationTestMixin


class PostsListTests(PublicationTestMixin, TestCase):
    def test_AC_15_empty_state(self):
        response = self.client.get(reverse("social:posts"))
        self.assertContains(response, "Nenhuma publicação ainda")
        self.assertContains(response, reverse("social:post_new"))

    def test_AC_15_lists_only_own_newest_first_with_summary_and_thumbnail(self):
        old = self.make_publication(self.make_accounts(1), text="Publicação antiga")
        new = self.make_publication(self.make_accounts(1, start=5), text="Publicação nova " + "x" * 300, send=True)
        Publication.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        theirs = self.make_publication(self.make_accounts(1, owner=self.bob, start=9), owner=self.bob, text="Do Bob")
        response = self.client.get(reverse("social:posts"))
        html = response.content.decode()
        self.assertLess(html.index("Publicação nova"), html.index("Publicação antiga"))
        self.assertNotContains(response, "Do Bob")
        self.assertContains(response, reverse("social:post_image", args=[new.pk]))
        self.assertNotContains(response, reverse("social:post_image", args=[theirs.pk]))
        self.assertNotContains(response, "x" * 200)  # texto resumido
        self.assertContains(response, "Publicada")      # a nova foi enviada
        self.assertContains(response, "Pendente")       # a antiga não
        self.assertContains(response, "1 publicada(s)")

    def test_AC_15_failed_publications_show_the_failure_count(self):
        from apps.social.services.meta import MetaApiError

        pub = self.make_publication(self.make_accounts(2))
        self.publish.side_effect = [{"photo_id": "p", "post_id": "1_1"}, MetaApiError("x", code=368)]
        from apps.social.services import publishing
        publishing.send_pending(pub)
        response = self.client.get(reverse("social:posts"))
        self.assertContains(response, "Com falhas")
        self.assertContains(response, "1 com falha")

    def test_AC_15_html_in_text_is_escaped(self):
        self.make_publication(text="<img src=x onerror=alert(1)>")
        response = self.client.get(reverse("social:posts"))
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")

    def test_AC_18_other_users_publications_are_hidden_from_the_history(self):
        self.make_publication(self.make_accounts(1, owner=self.bob, start=9), owner=self.bob, text="Segredo do Bob")
        self.assertNotContains(self.client.get(reverse("social:posts")), "Segredo do Bob")

    def test_navigation_keeps_publications_active_on_related_pages(self):
        pub = self.make_publication()
        for url in (reverse("social:posts"), reverse("social:post_new"), reverse("social:post_detail", args=[pub.pk])):
            with self.subTest(url):
                items = {i["label"]: i["active"] for i in self.client.get(url).context["nav_items"]}
                self.assertTrue(items["Publicações"])
                self.assertFalse(items["Contas conectadas"])
