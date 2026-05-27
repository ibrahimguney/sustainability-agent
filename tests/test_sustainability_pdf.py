import unittest

from sustainability_pdf import clean_text, search_keywords_in_pdf_pages, split_into_sentences


class SustainabilityPdfTest(unittest.TestCase):
    def test_clean_text_collapses_whitespace(self):
        self.assertEqual(clean_text(" Scope 1\n   emissions  "), "Scope 1 emissions")

    def test_search_keywords_in_pdf_pages_returns_evidence(self):
        pages = [
            {
                "page": 1,
                "clean_text": "Scope 1 emissions were 2500 kg CO2e. Other long sentence for context.",
            }
        ]

        result = search_keywords_in_pdf_pages(pages, ["Scope 1"], context_sentences=0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "page"], 1)
        self.assertEqual(result.loc[0, "keyword"], "Scope 1")
        self.assertIn("Scope 1 emissions", result.loc[0, "evidence_text"])

    def test_split_into_sentences_filters_short_fragments(self):
        sentences = split_into_sentences("Short. This is a long enough sentence for extraction.")
        self.assertEqual(sentences, ["This is a long enough sentence for extraction."])


if __name__ == "__main__":
    unittest.main()