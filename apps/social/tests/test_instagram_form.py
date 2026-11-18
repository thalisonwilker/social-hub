from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.social.forms import PublicationForm
from apps.social.models import SocialAccount

from .image_helpers import make_image_bytes
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS, make_threads_account

IG = SocialAccount.Platform.INSTAGRAM


def upload(size=(800, 800), fmt="JPEG"):
    return SimpleUploadedFile("f.jpg", make_image_bytes(fmt=fmt, size=size), content_type="image/jpeg")


@override_settings(**THREADS_SETTINGS)
class InstagramFormTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page)

    def form(self, *, accounts=None, text="Legenda #ok", image="default", **extra):
        accounts = accounts if accounts is not None else [self.ig]
        data = {"text": text, "accounts": [a.pk for a in accounts]}
        files = {}
        if image == "default":
            files["image"] = upload()
        elif image is not None:
            files["image"] = image
        return PublicationForm({**data, **extra}, files, user=self.alice)

    # ---- AC-6 --------------------------------------------------------------
    def test_AC_6_image_is_required(self):
        form = self.form(image=None)
        self.assertFalse(form.is_valid())
        self.assertIn("Instagram", form.errors["image"][0])

    def test_AC_6_valid_instagram_only_publication(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNotNone(form.sanitized)

    # ---- AC-7 --------------------------------------------------------------
    def test_AC_7_aspect_ratio_limits(self):
        cases = [
            ((800, 1000), True),   # 0,8 exato
            ((1910, 1000), True),  # 1,91 exato
            ((800, 1001), False),  # < 0,8
            ((1911, 1000), False),  # > 1,91
            ((1000, 400), False),
            ((400, 1000), False),
        ]
        for size, ok in cases:
            with self.subTest(size=size):
                form = self.form(image=upload(size))
                self.assertEqual(form.is_valid(), ok, form.errors)
                if not ok:
                    self.assertIn("4:5", form.errors["image"][0])

    def test_AC_7_minimum_width(self):
        form = self.form(image=upload((319, 319)))
        self.assertFalse(form.is_valid())
        self.assertIn("320", form.errors["image"][0])
        self.assertTrue(self.form(image=upload((320, 320))).is_valid())

    # ---- AC-8 --------------------------------------------------------------
    def test_AC_8_caption_length_limit(self):
        self.assertTrue(self.form(text="a" * 2200).is_valid())
        form = self.form(text="a" * 2201)
        self.assertFalse(form.is_valid())
        self.assertIn("2200", form.errors["text"][0])
        self.assertIn("2201", form.errors["text"][0])

    def test_AC_8_hashtag_limit(self):
        self.assertTrue(self.form(text=" ".join(f"#t{i}" for i in range(30))).is_valid())
        form = self.form(text=" ".join(f"#t{i}" for i in range(31)))
        self.assertFalse(form.is_valid())
        self.assertIn("30", form.errors["text"][0])

    def test_AC_8_limits_do_not_apply_without_instagram(self):
        form = self.form(accounts=[make_threads_account(self.alice, "900")], text=" ".join(f"#t{i}" for i in range(40)))
        self.assertTrue(form.is_valid(), form.errors)

    # ---- AC-9 --------------------------------------------------------------
    @override_settings(PUBLIC_BASE_URL="", THREADS_REDIRECT_URI="http://localhost/cb")
    def test_AC_9_public_address_is_required(self):
        form = self.form()
        self.assertFalse(form.is_valid())
        self.assertIn("PUBLIC_BASE_URL", form.errors["image"][0])

    # ---- AC-10 -------------------------------------------------------------
    def test_AC_10_mixed_destinations_and_instagram_rules_only_when_marked(self):
        threads = make_threads_account(self.alice, "900")
        fb = self.make_accounts(1)[0]
        form = self.form(accounts=[self.ig, threads, fb])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual({a.platform for a in form.cleaned_data["accounts"]}, {IG, "threads", "facebook_page"})
        # sem Instagram, uma proporção extrema segue valendo só pela regra do Threads/Facebook
        wide = self.form(accounts=[fb], image=upload((1500, 400)))
        self.assertTrue(wide.is_valid(), wide.errors)

    def test_AC_10_other_users_instagram_is_an_invalid_choice(self):
        bob_page = make_page(self.bob, "9")
        bob_ig = make_instagram(self.bob, bob_page, external_id="999")
        form = self.form(accounts=[bob_ig])
        self.assertFalse(form.is_valid())
        self.assertIn("accounts", form.errors)

    def test_AC_10_reauth_instagram_is_not_selectable(self):
        SocialAccount.objects.filter(pk=self.ig.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        self.assertFalse(self.form().is_valid())
