from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase


class NoPublicMediaTests(TestCase):
    def test_AC_17_media_paths_are_not_served_even_to_logged_in_users(self):
        # As imagens só saem pela view autenticada; nenhuma rota serve MEDIA_ROOT.
        self.client.force_login(get_user_model().objects.create_user("alice", password="x"))
        for path in ("/media/publications/x.jpg", "/publications/x.jpg"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class PublicationConfigTests(SimpleTestCase):

    def test_limits_match_the_design(self):
        self.assertEqual(settings.PUBLISH_BATCH_SIZE, 5)
        self.assertEqual(settings.PUBLICATION_MAX_IMAGE_BYTES, 8 * 1024 * 1024)
        self.assertEqual(settings.PUBLICATION_MAX_IMAGE_PIXELS, 40_000_000)
        self.assertEqual(settings.PUBLICATION_MAX_TEXT_LENGTH, 5000)
        self.assertEqual(settings.META_UPLOAD_TIMEOUT, 30)
        # lote x timeout de upload precisa caber no timeout do Gunicorn (180 s)
        self.assertLess(settings.PUBLISH_BATCH_SIZE * settings.META_UPLOAD_TIMEOUT, 180)

    def test_media_root_is_outside_static_files(self):
        self.assertNotIn(str(settings.MEDIA_ROOT), [str(d) for d in settings.STATICFILES_DIRS])
