import unittest
from unittest.mock import patch

from job_agent.database.mongo import reset_in_memory_storage
from job_agent.services.resume_knowledge_service import (
    build_resume_context,
    chunk_resume_text,
    index_resume_content,
    search_profile_knowledge,
)


class ResumeKnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        reset_in_memory_storage()

    def test_chunk_resume_text_breaks_large_text(self):
        text = ("Backend Engineer at Air India. " * 80).strip()

        chunks = chunk_resume_text(text, max_chars=120, overlap=20)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk for chunk in chunks))

    def test_index_and_search_resume_content_from_text_file(self):
        with patch(
            "job_agent.services.resume_knowledge_service.generate_embedding",
            side_effect=lambda text: [float(len(text)), float(text.lower().count("air india"))],
        ), patch(
            "job_agent.services.resume_knowledge_service.groq_json_completion",
            return_value=None,  # Force fallback chunking
        ):
            count = index_resume_content(
                b"Air India Backend Engineer\nWorked on booking systems.\n",
                filename="resume.txt",
                content_type="text/plain",
            )
            context = build_resume_context("Air India")

        self.assertGreater(count, 0)  # At least one chunk should be created
        self.assertIn("Air India", context or "")

    def test_profile_scoped_resume_knowledge_does_not_leak_between_profiles(self):
        with patch(
            "job_agent.services.resume_knowledge_service.generate_embedding",
            side_effect=lambda text: [float(len(text)), float("air india" in text.lower()), float("openai" in text.lower())],
        ), patch(
            "job_agent.services.resume_knowledge_service.ensure_resume_knowledge_index",
            return_value=1,
        ):
            index_resume_content(
                b"Air India Backend Engineer\nBuilt booking systems.\n",
                filename="candidate-a.txt",
                content_type="text/plain",
                profile_id="candidate-a",
                resume_file_id="resume-a",
            )
            index_resume_content(
                b"OpenAI Research Engineer\nWorked on LLM systems.\n",
                filename="candidate-b.txt",
                content_type="text/plain",
                profile_id="candidate-b",
                resume_file_id="resume-b",
            )

            matches_a = search_profile_knowledge("Air India", profile_id="candidate-a")
            matches_b = search_profile_knowledge("Air India", profile_id="candidate-b")

        self.assertTrue(matches_a)
        self.assertEqual(matches_b, [])
