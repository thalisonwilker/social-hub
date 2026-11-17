import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from apps.social.images import ImageValidationError, sanitize_image

from .image_helpers import make_image_bytes, make_upload


def result_image(sanitized):
    return Image.open(io.BytesIO(sanitized.content.read()))


class SanitizeImageTests(SimpleTestCase):
    def test_AC_6_valid_jpeg_and_png_are_accepted(self):
        jpeg = sanitize_image(make_upload("a.jpg"))
        self.assertEqual((jpeg.content_type, jpeg.extension), ("image/jpeg", ".jpg"))
        png = sanitize_image(make_upload("a.png", "image/png", fmt="PNG"))
        self.assertEqual((png.content_type, png.extension), ("image/png", ".png"))
        self.assertEqual(result_image(png).format, "PNG")

    def test_AC_6_exif_is_removed_and_orientation_is_applied_first(self):
        exif = Image.Exif()
        exif[0x010F] = "CameraMaker"
        exif[0x0112] = 6  # rotacionar 90°: 40x20 vira 20x40
        original = make_upload(exif=exif.tobytes())
        self.assertIn(b"CameraMaker", original.read())
        original.seek(0)
        sanitized = sanitize_image(original)
        out = sanitized.content.read()
        self.assertNotIn(b"CameraMaker", out)
        image = Image.open(io.BytesIO(out))
        self.assertEqual(len(image.getexif()), 0)
        self.assertEqual(image.size, (20, 40))

    def test_AC_6_filename_is_random_and_never_the_original(self):
        a = sanitize_image(make_upload("minha-foto-secreta.jpg"))
        b = sanitize_image(make_upload("minha-foto-secreta.jpg"))
        self.assertNotIn("secreta", a.content.name)
        self.assertNotEqual(a.content.name, b.content.name)
        self.assertRegex(a.content.name, r"^[0-9a-f]{32}\.jpg$")

    def test_edge_png_transparency_stays_png_with_alpha(self):
        upload = make_upload("t.png", "image/png", fmt="PNG", mode="RGBA", color=(1, 2, 3, 0))
        sanitized = sanitize_image(upload)
        self.assertEqual(result_image(sanitized).mode, "RGBA")

    def test_AC_5_extension_lies_content_wins(self):
        # JPEG real com extensão .png é aceito pelo conteúdo; texto com extensão .jpg é rejeitado.
        ok = sanitize_image(make_upload("enganosa.png", "image/png"))
        self.assertEqual(ok.content_type, "image/jpeg")
        fake = SimpleUploadedFile("falsa.jpg", b"<html>nao sou imagem</html>", content_type="image/jpeg")
        with self.assertRaises(ImageValidationError):
            sanitize_image(fake)

    def test_AC_5_other_formats_are_rejected(self):
        for fmt, name in (("GIF", "a.gif"), ("WEBP", "a.webp"), ("BMP", "a.bmp")):
            with self.subTest(fmt):
                with self.assertRaises(ImageValidationError) as ctx:
                    sanitize_image(make_upload(name, f"image/{fmt.lower()}", fmt=fmt))
                self.assertIn("JPEG ou PNG", str(ctx.exception))
        svg = SimpleUploadedFile("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', content_type="image/svg+xml")
        with self.assertRaises(ImageValidationError):
            sanitize_image(svg)

    def test_AC_5_empty_missing_and_truncated_files_are_rejected(self):
        for upload in (None, SimpleUploadedFile("v.jpg", b"", content_type="image/jpeg")):
            with self.assertRaises(ImageValidationError):
                sanitize_image(upload)
        truncated = SimpleUploadedFile("t.jpg", make_image_bytes(size=(200, 200))[:80], content_type="image/jpeg")
        with self.assertRaises(ImageValidationError):
            sanitize_image(truncated)

    @override_settings(PUBLICATION_MAX_IMAGE_BYTES=500)
    def test_AC_5_too_many_bytes_is_rejected(self):
        with self.assertRaises(ImageValidationError) as ctx:
            sanitize_image(make_upload(size=(300, 300), fmt="PNG"))
        self.assertIn("no máximo", str(ctx.exception))

    @override_settings(PUBLICATION_MAX_IMAGE_PIXELS=100)
    def test_AC_5_too_many_pixels_is_rejected(self):
        with self.assertRaises(ImageValidationError) as ctx:
            sanitize_image(make_upload(size=(20, 20)))
        self.assertIn("grande demais", str(ctx.exception))
        sanitize_image(make_upload(size=(10, 10)))  # no limite passa


class AspectRatioTests(SimpleTestCase):
    def test_AC_3_dimensions_are_reported_after_orientation(self):
        """AC-3: largura/altura da imagem sanitizada acompanham a orientação aplicada."""
        sanitized = sanitize_image(make_upload(size=(40, 20)))
        self.assertEqual((sanitized.width, sanitized.height), (40, 20))

    def test_AC_3_ratio_limit_is_inclusive_and_symmetric(self):
        """AC-3: 10:1 é aceito; acima disso é recusado em qualquer sentido."""
        from apps.social.images import aspect_ratio_within

        self.assertTrue(aspect_ratio_within(1000, 100, 10))
        self.assertTrue(aspect_ratio_within(100, 1000, 10))
        self.assertFalse(aspect_ratio_within(1001, 100, 10))
        self.assertFalse(aspect_ratio_within(100, 1001, 10))
        self.assertFalse(aspect_ratio_within(0, 100, 10))

    def test_AC_3_small_and_large_images_are_not_blocked_by_ratio_helper(self):
        """AC-3: largura < 320 ou > 4096 não entram na regra de proporção."""
        from apps.social.images import aspect_ratio_within

        self.assertTrue(aspect_ratio_within(200, 200, 10))
        self.assertTrue(aspect_ratio_within(5000, 4000, 10))
