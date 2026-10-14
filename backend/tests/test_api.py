import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from cards.bandai import normalize_card
from cards.importer import upsert_cards
from cards.models import Card, CardFingerprint
from scans.models import Scan
from vision import fingerprint as fp
from vision.preprocess import encode_jpeg

from .synthetic import make_card, make_photo

MEDIA = tempfile.mkdtemp()

BANDAI_LEADER = {
    "id": 4,
    "card_name": "Champa",
    "card_number": "BT1-001",
    "card_text": "[Auto] ...",
    "image_url": "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001.png",
    "card_set": "Booster Pack ～GALACTIC BATTLE～ [DBS-B01]",
    "card_config": [
        {"config_name": "Type", "value": "LEADER"},
        {"config_name": "Rarity", "value": "Rare[R]"},
        {"config_name": "Energy"},
        {"config_name": "Power", "value": "10000"},
        {"config_name": "Era", "value": "Champa Saga"},
        {"config_name": "Notes", "value": ""},
    ],
    "backcard_card_name": "God of Destruction Champa",
    "backcard_card_text": "[Auto] When this card attacks, draw 1 card.",
    "backcard_image_url": "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001_b.png",
    "backcard_card_config": [{"config_name": "Power", "value": "15000"}],
    "regulations": [{"id": 1, "title": "Constructed"}],
}


class NormalizeCardTests(TestCase):
    def test_bandai_record(self):
        data = normalize_card(BANDAI_LEADER)
        self.assertEqual(data["bandai_id"], 4)
        self.assertEqual(data["card_number"], "BT1-001")
        self.assertEqual(data["set_code"], "BT1")
        self.assertEqual(data["card_type"], "LEADER")
        self.assertEqual(data["rarity"], "Rare[R]")
        self.assertEqual(data["power"], "10000")
        self.assertEqual(data["cost"], "")
        self.assertEqual(data["back_name"], "God of Destruction Champa")
        self.assertTrue(data["image_back_url"].endswith("BT1-001_b.png"))
        self.assertEqual(
            data["attributes"],
            {"Era": "Champa Saga", "Back Power": "15000", "Regulations": ["Constructed"]},
        )

    def test_invalid_record(self):
        self.assertIsNone(normalize_card({"card_name": "Sin id ni número"}))

    def test_alt_arts_are_separate_cards(self):
        alt = {**BANDAI_LEADER, "id": 1088, "image_url": "https://x/BT1-001_PR.png"}
        self.assertEqual(upsert_cards([BANDAI_LEADER, alt]).created, 2)
        self.assertEqual(Card.objects.filter(card_number="BT1-001").count(), 2)

    def test_upsert_is_idempotent(self):
        upsert_cards([BANDAI_LEADER])
        renamed = {**BANDAI_LEADER, "card_name": "Champa!"}
        stats = upsert_cards([renamed])
        self.assertEqual((stats.created, stats.updated, stats.unchanged), (0, 1, 0))
        self.assertEqual(upsert_cards([renamed]).unchanged, 1)


@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=True)
class ScanApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.cards = []
        for seed in range(10):
            card = Card.objects.create(
                bandai_id=seed + 1, card_number=f"BT1-{seed:03d}", name=f"Carta {seed}"
            )
            prints = fp.compute(make_card(seed))
            CardFingerprint.objects.create(
                card=card,
                source_url=f"https://example.com/{seed}.png",
                phash=prints.phash,
                dhash=prints.dhash,
                orb=prints.orb,
                orb_count=prints.orb_count,
            )
            self.cards.append(card)

    def test_upload_scan_identifies_card(self):
        upload = SimpleUploadedFile(
            "foto.jpg", encode_jpeg(make_photo(make_card(4))), content_type="image/jpeg"
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {"image": upload}, format="multipart")
        self.assertEqual(response.status_code, 202)

        detail = self.client.get(f"/api/scans/{response.data['id']}/").data
        self.assertEqual(detail["status"], Scan.Status.DONE)
        self.assertEqual(detail["matched_card"]["card_number"], "BT1-004")
        self.assertFalse(detail["needs_review"])
        self.assertTrue(detail["cropped_image"])
        self.assertEqual(detail["candidates"][0]["card_number"], "BT1-004")

    def _upload(self, card_seed):
        upload = SimpleUploadedFile(
            "foto.jpg", encode_jpeg(make_photo(make_card(card_seed))), content_type="image/jpeg"
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {"image": upload}, format="multipart")
        return self.client.get(f"/api/scans/{response.data['id']}/").data

    def test_confirm_learns_uncatalogued_printing(self):
        # Seed 99: "impresión" que no está en el catálogo (p. ej. una promo).
        first = self._upload(99)
        self.assertTrue(first["needs_review"])

        target = self.cards[3]
        response = self.client.post(
            f"/api/scans/{first['id']}/confirm/", {"card_id": target.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["confirmed"])
        self.assertFalse(response.data["needs_review"])
        self.assertEqual(response.data["matched_card"]["id"], target.id)
        self.assertTrue(CardFingerprint.objects.filter(card=target, face="scan").exists())

        # La siguiente foto de esa misma impresión ya se reconoce sola.
        second = self._upload(99)
        self.assertEqual(second["matched_card"]["id"], target.id)
        self.assertFalse(second["needs_review"])

    def test_confirm_rejects_unfinished_scan(self):
        scan = Scan.objects.create(source=Scan.Source.CAMERA)
        response = self.client.post(
            f"/api/scans/{scan.id}/confirm/", {"card_id": self.cards[0].id}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(CAMERA_URL="")
    def test_camera_scan_without_camera_fails_gracefully(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/scans/", {}, format="json")
        scan = Scan.objects.get(pk=response.data["id"])
        self.assertEqual(scan.source, Scan.Source.CAMERA)
        self.assertEqual(scan.status, Scan.Status.FAILED)
        self.assertIn("CAMERA_URL", scan.error)

    @override_settings(CAMERA_URL="http://camera:8080")
    def test_camera_preview_proxies_frame(self):
        with mock.patch("scans.camera.requests.get") as get:
            get.return_value.content = b"\xff\xd8jpeg"
            response = self.client.get("/api/camera/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")


class CollectionApiTests(TestCase):
    def test_adding_same_card_sums_quantity(self):
        card = Card.objects.create(bandai_id=31, card_number="BT1-031", name="Son Goku")
        client = APIClient()
        first = client.post("/api/collection/", {"card_id": card.id, "quantity": 2}, format="json")
        second = client.post("/api/collection/", {"card_id": card.id, "quantity": 1}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["quantity"], 3)


class ImageCacheTests(TestCase):
    def test_local_path_mirrors_cdn(self):
        from cards.images import local_path

        with override_settings(CARD_IMAGES_DIR="/cache"):
            path = local_path("https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001_b.png")
        self.assertEqual(str(path), "/cache/DB-EN/BT1/BT1-001_b.png")

    def test_get_image_prefers_cache(self):
        from cards.images import get_image

        with tempfile.TemporaryDirectory() as tmp, override_settings(CARD_IMAGES_DIR=tmp):
            url = "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001.png"
            with mock.patch("cards.images._session") as session:
                session.return_value.get.return_value.content = b"png"
                self.assertEqual(get_image(url), b"png")
                self.assertEqual(get_image(url), b"png")
            self.assertEqual(session.return_value.get.call_count, 1)


class FacetsTests(TestCase):
    def test_facets_have_no_duplicates(self):
        for i, color in enumerate(["Red", "Blue", "Red"]):
            Card.objects.create(bandai_id=i + 1, card_number=f"BT1-{i:03d}", name="X", color=color)
        facets = APIClient().get("/api/cards/facets/").data
        self.assertEqual(facets["color"], ["Blue", "Red"])
