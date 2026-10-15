import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from ai_tailor import GeminiAnalysisError, GeminiJobAnalyzer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class GeminiJobAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.response = Mock()
        self.client.models.generate_content.return_value = self.response
        self.analyzer = GeminiJobAnalyzer(config_path=str(CONFIG_PATH), client=self.client)

    def set_response(self, data):
        self.response.text = json.dumps(data)

    def test_analyzes_gmail_collector_record_and_applies_threshold(self):
        self.set_response(
            {
                "match_score": 82,
                "matching_skills": ["Java", "Spring Boot"],
                "missing_keywords": ["Kubernetes"],
                "summary": "Strong match for the role.",
            }
        )

        result = self.analyzer.analyze_job(
            {
                "subject": "Senior Java Engineer",
                "sender": "jobs@example.com",
                "source": "LinkedIn",
                "body": "We need Java and Spring Boot experience.",
            },
            "Experienced Java engineer with Spring Boot experience.",
        )

        self.assertEqual(result["match_score"], 82)
        self.assertEqual(result["matching_skills"], ["Java", "Spring Boot"])
        self.assertEqual(result["missing_keywords"], ["Kubernetes"])
        self.assertTrue(result["eligible_for_draft"])
        self.client.models.generate_content.assert_called_once()
        call = self.client.models.generate_content.call_args.kwargs
        self.assertEqual(call["model"], self.analyzer.model)
        self.assertIn("Senior Java Engineer", call["contents"])

    def test_marks_score_below_configured_threshold_ineligible(self):
        self.set_response(
            {
                "match_score": 74,
                "matching_skills": ["Java"],
                "missing_keywords": ["Spring Boot"],
                "summary": "Some relevant experience, but key skills are missing.",
            }
        )

        result = self.analyzer.analyze_job("Java developer role", "Java developer profile")

        self.assertFalse(result["eligible_for_draft"])

    def test_rejects_invalid_json_response(self):
        self.response.text = "not json"

        with self.assertRaisesRegex(GeminiAnalysisError, "invalid JSON"):
            self.analyzer.analyze_job("Java developer role", "Java developer profile")

    def test_rejects_out_of_range_match_score(self):
        self.set_response(
            {
                "match_score": 101,
                "matching_skills": [],
                "missing_keywords": [],
                "summary": "Invalid score.",
            }
        )

        with self.assertRaisesRegex(GeminiAnalysisError, "0–100"):
            self.analyzer.analyze_job("Java developer role", "Java developer profile")

    def test_wraps_gemini_request_failure(self):
        self.client.models.generate_content.side_effect = TimeoutError("request timed out")

        with self.assertRaisesRegex(GeminiAnalysisError, "Gemini request failed") as error:
            self.analyzer.analyze_job("Java developer role", "Java developer profile")

        self.assertIsInstance(error.exception.__cause__, TimeoutError)

    def test_rejects_empty_job_description(self):
        with self.assertRaisesRegex(ValueError, "job description is empty"):
            self.analyzer.analyze_job({"subject": "No description"}, "Profile text")


if __name__ == "__main__":
    unittest.main()
