import base64
import unittest
import tests
from drishya.protocol import smol_request, parse_smol
from qa.legacy.mirage_protocol import format_mirage


class ProtocolTests(unittest.TestCase):
    def test_image_is_inline_and_prompt_is_bounded(self):
        request = smol_request(b"PNG", "concise")
        self.assertFalse(request["stream"])
        self.assertLessEqual(request["max_tokens"], 200)
        content = request["messages"][0]["content"]
        self.assertIn("visible", content[0]["text"].lower())
        self.assertEqual(content[1]["image_url"]["url"],
                         "data:image/png;base64," + base64.b64encode(b"PNG").decode())

    def test_detailed_has_more_room(self):
        self.assertGreater(smol_request(b"x", "detailed")["max_tokens"],
                           smol_request(b"x", "concise")["max_tokens"])

    def test_invalid_detail_rejected(self):
        with self.assertRaises(ValueError):
            smol_request(b"x", "unknown")

    def test_bad_response_is_actionable(self):
        for payload in [{}, {"choices": []}, {"choices": [{"message": {"content": " "}}]}]:
            with self.assertRaises(ValueError):
                parse_smol(payload)

    def test_smol_preserves_actual_description(self):
        self.assertEqual(parse_smol({"choices": [{"message": {"content": " A red cup. "}}]}),
                         "A red cup.")

    def test_concise_result_is_bounded_and_has_complete_sentences(self):
        text = "A red cup is on a desk. " * 20 + "An unfinished fragment"
        output = parse_smol({"choices": [{"message": {"content": text}}]}, "concise")
        self.assertLessEqual(len(output.split()), 90)
        self.assertEqual(output.count("."), 4)
        self.assertTrue(output.endswith("."))

    def test_detailed_result_keeps_more_sentences(self):
        payload = {"choices": [{"message": {"content": "A cup is on a desk. " * 20}}]}
        self.assertGreater(len(parse_smol(payload, "detailed")), len(parse_smol(payload, "concise")))

    def test_mirage_scene_and_text(self):
        output = format_mirage({"scene": "A desk with a red cup.",
                                "text": [{"text": "Hello"}]}, "detailed")
        self.assertIn("A desk with a red cup.", output)
        self.assertIn("Hello", output)

    def test_mirage_missing_scene_has_object_fallback(self):
        self.assertIn("cup", format_mirage({"objects": [{"name": "cup"}]}, "concise"))

    def test_concise_mirage_includes_subject_when_scene_is_present(self):
        text = format_mirage({"scene": {"style": "graphic"},
                              "objects": [{"name": "red circle"}, {"name": "blue square"}]}, "concise")
        self.assertIn("red circle", text)
        self.assertIn("blue square", text)

    def test_mirage_empty_is_not_success(self):
        with self.assertRaises(ValueError):
            format_mirage({}, "concise")

    def test_published_mirage_structured_scene_and_ocr(self):
        output = format_mirage({"scene": {"background": "white", "style": "digital interface"},
                                "objects": [{"name": "button", "position": "bottom right",
                                             "description": {"color": "blue"}}],
                                "text": [{"string": "Upload", "score": .8}]}, "detailed")
        self.assertIn("digital interface", output)
        self.assertIn("white", output)
        self.assertIn("Upload", output)
