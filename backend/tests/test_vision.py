from django.test import SimpleTestCase

from vision import fingerprint as fp
from vision.matcher import FingerprintIndex, identify
from vision.preprocess import CARD_H, CARD_W, extract_card

from .synthetic import make_card, make_photo


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
