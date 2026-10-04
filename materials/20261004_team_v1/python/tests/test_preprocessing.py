import unittest

from scamlens.preprocessing import (
    defang_url,
    extract_urls,
    mask_sensitive_text,
    neutralize_url_placeholder,
    normalize_text,
)


class PreprocessingTests(unittest.TestCase):
    def test_extract_and_defang_url(self):
        text = "확인 https://secure-check.invalid/login 바랍니다"
        self.assertEqual(extract_urls(text), ["https://secure-check.invalid/login"])
        self.assertEqual(
            defang_url(extract_urls(text)[0]),
            "hxxps://secure-check[.]invalid/login",
        )
        self.assertEqual(
            defang_url("hxxps://secure-check[.]invalid/login"),
            "hxxps://secure-check[.]invalid/login",
        )

    def test_mask_phone_number_and_url(self):
        text = "010-1234-5678 https://example.invalid/a"
        self.assertEqual(mask_sensitive_text(text), "[PHONE] [URL]")

    def test_mask_non_mobile_korean_phone_numbers(self):
        # 유선·인터넷·무료·안심·대표번호도 실사용 식별자다.
        for number in (
            "02-123-4567",
            "032-565-3300",
            "061-652-9888",
            "070-4567-8901",
            "080-863-5533",
            "0505-123-4567",
            "1588-1234",
            "1644-5678",
        ):
            with self.subTest(number=number):
                self.assertEqual(mask_sensitive_text(number), "[PHONE]")

    def test_mask_grouped_card_and_account_numbers(self):
        # 4자리씩 끊긴 번호는 연속 숫자 마스크가 잡지 못한다.
        self.assertEqual(mask_sensitive_text("9891-8878-6783-2564"), "[CARD]")
        self.assertEqual(mask_sensitive_text("110-234-567890"), "[NUMBER]")

    def test_mask_space_separated_account_number(self):
        # 계좌번호는 하이픈 대신 공백으로 끊겨 오기도 한다.
        self.assertEqual(mask_sensitive_text("계좌 1005 581 2853 입금"), "계좌 [NUMBER] 입금")

    def test_mask_international_and_document_numbers(self):
        # 국제형식 번호의 지역번호는 한 자리다.
        self.assertEqual(mask_sensitive_text("82-2-6343-9000"), "[NUMBER]")
        self.assertEqual(mask_sensitive_text("82 2-360-2152"), "[NUMBER]")
        self.assertEqual(mask_sensitive_text("2025-14016-1"), "[NUMBER]")

    def test_trailing_hyphen_does_not_block_masking(self):
        # 번호 뒤의 하이픈은 한국어 문장부호일 뿐 번호의 일부가 아니다.
        self.assertEqual(mask_sensitive_text("센터(1599-1111->"), "센터([PHONE]->")
        self.assertEqual(mask_sensitive_text("080-019-7000-앱"), "[PHONE]-앱")

    def test_following_number_word_does_not_block_masking(self):
        # ``3791 1번``의 공백 뒤 숫자는 번호의 연장이 아니라 다음 낱말이다.
        self.assertEqual(
            mask_sensitive_text("☎02-3297-3791 1번 대출"),
            "☎[PHONE] 1번 대출",
        )

    def test_masking_leaves_dates_and_short_numbers_intact(self):
        for value in (
            "2024-08-01",
            "2024 08 01",
            "오후 2-3시",
            "12-34",
            "1-2-3",
            "50,000원",
        ):
            with self.subTest(value=value):
                self.assertEqual(mask_sensitive_text(value), value)

    def test_mask_email_and_resident_number(self):
        # 여정 검증기가 이 둘을 거부하므로 공유 마스킹이 함께 처리해야 한다.
        self.assertEqual(mask_sensitive_text("문의 hong@example.com 주세요"), "문의 [EMAIL] 주세요")
        self.assertEqual(mask_sensitive_text("900101-1234567"), "[RRN]")

    def test_bare_www_marker_is_defanged(self):
        # 호스트 없는 ``www.``는 링크가 아니지만 감사에서 활성 URL과 구분되지 않는다.
        self.assertEqual(mask_sensitive_text("주민 www. 국민"), "주민 www[.] 국민")
        self.assertEqual(mask_sensitive_text("www.example.invalid"), "[URL]")

    def test_dangling_url_scheme_does_not_survive(self):
        # 스킴 뒤에 공백이 있으면 본문만 치환돼 스킴이 남았다.
        self.assertEqual(mask_sensitive_text("https:// example.invalid/a"), "[URL]")
        self.assertEqual(mask_sensitive_text("확인 https:// bit.ly/x"), "확인 [URL]")
        self.assertEqual(mask_sensitive_text("https://"), "[URL]")
        self.assertEqual(normalize_text("안내 https:// example.invalid/a"), "안내 [url]")

    def test_mask_multiple_urls_in_one_pass(self):
        text = "https://a.invalid/x https://a.invalid/x/y"
        self.assertEqual(mask_sensitive_text(text), "[URL] [URL]")

    def test_extract_preserves_repeated_url_occurrences(self):
        text = "https://a.invalid/x https://a.invalid/x"
        self.assertEqual(
            extract_urls(text),
            ["https://a.invalid/x", "https://a.invalid/x"],
        )

    def test_extracts_and_defangs_bare_short_domain(self):
        text = "배송조회 bit.ly/example"
        self.assertEqual(extract_urls(text), ["bit.ly/example"])
        self.assertEqual(defang_url("bit.ly/example"), "bit[.]ly/example")
        self.assertEqual(mask_sensitive_text(text), "배송조회 [URL]")

    def test_extracts_url_attached_to_korean_text(self):
        text = "행동요령참조https://example.invalid/guide."
        self.assertEqual(
            extract_urls(text),
            ["https://example.invalid/guide"],
        )
        self.assertEqual(mask_sensitive_text(text), "행동요령참조[URL]")

    def test_nfkc_does_not_activate_full_width_url(self):
        text = "확인 ｈｔｔｐｓ：／／ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ／ａ"
        self.assertEqual(
            extract_urls(text),
            ["https://example.invalid/a"],
        )
        self.assertEqual(mask_sensitive_text(text), "확인 [URL]")
        self.assertEqual(normalize_text(text), "확인 [url]")

    def test_normalize_unicode_and_whitespace(self):
        self.assertEqual(normalize_text("  ＬＯＧＩＮ   확인  "), "login 확인")

    def test_normalize_recomposes_decomposed_hangul(self):
        decomposed = "배송지 확인"
        self.assertEqual(normalize_text(decomposed), "배송지 확인")

    def test_neutralize_url_placeholder_preserves_context(self):
        self.assertEqual(
            neutralize_url_placeholder("배송 [URL] 조회"),
            "배송 조회",
        )


if __name__ == "__main__":
    unittest.main()
