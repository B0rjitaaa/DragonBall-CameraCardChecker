import cv2
from django.test import SimpleTestCase

from vision import fingerprint as fp
from vision.matcher import FingerprintIndex, identify
from vision.preprocess import (
    CARD_H,
    CARD_W,
    decode_reference,
    extract_card,
    find_card_quad,
    order_points,
    prepare_reference,
)

from .synthetic import make_card, make_photo, make_stand_photo


def build_index(cards):
    prints = {i: fp.compute(card) for i, card in enumerate(cards)}
    index = FingerprintIndex.from_rows(
        (i, 100 + i, p.phash, p.dhash) for i, p in prints.items()
    )
    return index, lambda ids: {i: prints[i].orb for i in ids}


class PreprocessTests(SimpleTestCase):
    def test_detects_and_warps_card(self):
        crop, detected = extract_card(make_photo(make_card(1)))
        self.assertTrue(detected)
        self.assertEqual(crop.shape[:2], (CARD_H, CARD_W))


    def test_card_on_a_stand_over_a_dark_backdrop(self):
        # Montaje del modo ráfaga: carta apoyada en un soporte blanco delante de
        # un fondo oscuro que se sale del encuadre. El detector antiguo cogía el
        # fondo oscuro (más grande) en vez de la carta.
        import numpy as np

        photo, corners = make_stand_photo(make_card(3))
        quad = find_card_quad(photo)
        self.assertIsNotNone(quad)
        self.assertLess(np.abs(order_points(quad) - corners).max(), 15)


    def test_reference_with_transparent_margins_is_trimmed(self):
        # Cartas apaisadas (Z-Extra): lienzo vertical con la carta en medio y
        # franjas transparentes arriba y abajo.
        import cv2
        import numpy as np

        canvas = np.zeros((1254, 893, 4), np.uint8)
        canvas[309:947, :, :3] = 120
        canvas[309:947, :, 3] = 255
        img = decode_reference(cv2.imencode(".png", canvas)[1].tobytes())
        self.assertEqual(img.shape, (638, 893, 3))
        opaque = decode_reference(cv2.imencode(".png", canvas[..., :3])[1].tobytes())
        self.assertEqual(opaque.shape, (1254, 893, 3))


    def test_product_photo_reference_is_cropped_to_the_card(self):
        # Foto de tienda: cuadrada, carta sobre fondo blanco.
        import numpy as np

        card = make_card(5)
        photo = np.full((1000, 1000, 3), 255, np.uint8)
        photo[140:860, 242:758] = cv2.resize(card, (516, 720))
        ref = prepare_reference(photo)
        self.assertEqual(ref.shape[:2], (CARD_H, CARD_W))
        self.assertLess(fp.hamming(np.array([fp.compute(ref).phash]), fp.compute(card).phash)[0], 8)


class FingerprintTests(SimpleTestCase):
    def test_hashes_are_stable_and_distinct(self):
        a, b = fp.compute(make_card(1)), fp.compute(make_card(2))
        self.assertEqual(a.phash, fp.compute(make_card(1)).phash)
        self.assertNotEqual(a.phash, b.phash)
        self.assertGreater(a.orb_count, 0)

    def test_hamming_handles_signed_hashes(self):
        import numpy as np

        hashes = np.array([-1, 0, 1], dtype=np.int64)
        self.assertEqual(fp.hamming(hashes, 0).tolist(), [64, 0, 1])


class MatcherTests(SimpleTestCase):
    def setUp(self):
        self.cards = [make_card(seed) for seed in range(40)]
        self.index, self.load_orb = build_index(self.cards)

    def test_identifies_card_in_photo(self):
        for target in (3, 17, 31):
            result = identify(make_photo(self.cards[target]), self.index, self.load_orb)
            self.assertEqual(result.best.card_id, 100 + target)
            self.assertTrue(result.card_detected)

    def test_identifies_card_upside_down(self):
        result = identify(make_photo(self.cards[8], rotate_180=True), self.index, self.load_orb)
        self.assertEqual(result.best.card_id, 108)

    def test_empty_index(self):
        result = identify(make_photo(self.cards[0]), FingerprintIndex.from_rows([]), self.load_orb)
        self.assertIsNone(result.best)
        self.assertEqual(result.method, "none")
