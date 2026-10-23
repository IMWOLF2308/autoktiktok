import unittest

from core.content_rules import REQUIRED_OUTRO, caption_copies_review, prepare_voiceover


class ContentRulesTests(unittest.TestCase):
    def test_exact_outro_once_and_preserves_the_hook(self):
        hook = "Chỉ 5,7 triệu mà có cả thang máy?"
        result = prepare_voiceover(hook)
        self.assertEqual(result, hook + " " + REQUIRED_OUTRO)
        self.assertEqual(prepare_voiceover(result), result)
        repeated = f"{hook} {REQUIRED_OUTRO.upper()} {REQUIRED_OUTRO}"
        self.assertEqual(prepare_voiceover(repeated), result)

    def test_rejects_empty_voice_instead_of_reading_only_cta(self):
        for text in ("", " . ", REQUIRED_OUTRO):
            with self.subTest(text=text), self.assertRaises(ValueError):
                prepare_voiceover(text)

    def test_caption_is_independent_even_if_it_has_hashtags(self):
        script = "Căn phòng này có cửa sổ nhìn ra khoảng sân phía trước. Giá thuê được chủ nhà báo là 5,7 triệu mỗi tháng."
        self.assertTrue(caption_copies_review(script + " #phongtro #govap", script))
        self.assertTrue(caption_copies_review("Căn phòng này có cửa sổ nhìn ra khoảng sân phía trước! #govap", script))
        self.assertFalse(caption_copies_review("5,7 triệu: góc phòng có cửa sổ đáng xem ở Gò Vấp! #phongtro", script))
