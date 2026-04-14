import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_agent.services.resume_service import (
    ResumeStorageError,
    get_resume_upload_path,
    store_resume,
)


class FakeResumeBucket:
    def __init__(self):
        self.uploads = []
        self.deleted = []
        self.downloads = {}

    def upload_from_stream(self, filename, source, metadata=None):
        payload = source.read()
        self.uploads.append(
            {
                "filename": filename,
                "payload": payload,
                "metadata": metadata or {},
            }
        )
        file_id = "507f1f77bcf86cd799439011"
        self.downloads[file_id] = payload
        return file_id

    def delete(self, object_id):
        self.deleted.append(str(object_id))

    def download_to_stream(self, object_id, stream):
        stream.write(self.downloads[str(object_id)])


class ResumeServiceTests(unittest.TestCase):
    def test_store_resume_uploads_to_bucket_and_updates_profile(self):
        bucket = FakeResumeBucket()

        with patch("job_agent.services.resume_service.has_mongo_storage", return_value=True), patch(
            "job_agent.services.resume_service.has_resume_bucket",
            return_value=True,
        ), patch(
            "job_agent.services.resume_service.resume_bucket",
            bucket,
        ), patch(
            "job_agent.services.resume_service.get_profile",
            return_value={"resume_file_id": "507f1f77bcf86cd799439099"},
        ), patch(
            "job_agent.services.resume_service.update_profile_fields",
        ) as update_profile_fields, patch(
            "job_agent.services.resume_service.index_resume_content",
        ) as index_resume_content:
            result = store_resume(
                b"resume-bytes",
                filename="resume.pdf",
                content_type="application/pdf",
                attach_to_profile=True,
                profile_id="candidate-a",
            )

        self.assertEqual(result["resume_file_id"], "507f1f77bcf86cd799439011")
        self.assertEqual(result["profile_id"], "candidate-a")
        self.assertEqual(bucket.uploads[0]["filename"], "resume.pdf")
        self.assertEqual(bucket.uploads[0]["payload"], b"resume-bytes")
        update_profile_fields.assert_called_once()
        index_resume_content.assert_called_once_with(
            b"resume-bytes",
            "resume.pdf",
            "application/pdf",
            profile_id="candidate-a",
            resume_file_id="507f1f77bcf86cd799439011",
        )
        self.assertEqual(bucket.deleted, ["507f1f77bcf86cd799439099"])

    def test_store_resume_requires_mongo_bucket(self):
        with patch("job_agent.services.resume_service.has_mongo_storage", return_value=False), patch(
            "job_agent.services.resume_service.has_resume_bucket",
            return_value=False,
        ):
            with self.assertRaises(ResumeStorageError):
                store_resume(b"resume-bytes", filename="resume.pdf")

    def test_get_resume_upload_path_prefers_existing_local_path(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(b"resume")
            path = handle.name

        try:
            result = get_resume_upload_path({"resume_path": path}, profile_id="candidate-a")
            self.assertEqual(result, path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_get_resume_upload_path_materializes_gridfs_resume(self):
        bucket = FakeResumeBucket()
        file_id = "507f1f77bcf86cd799439011"
        bucket.downloads[file_id] = b"resume-from-gridfs"

        with patch("job_agent.services.resume_service.has_mongo_storage", return_value=True), patch(
            "job_agent.services.resume_service.has_resume_bucket",
            return_value=True,
        ), patch(
            "job_agent.services.resume_service.resume_bucket",
            bucket,
        ):
            path = get_resume_upload_path(
                {
                    "profile_id": "candidate-a",
                    "resume_file_id": file_id,
                    "resume_filename": "resume.pdf",
                },
                profile_id="candidate-a",
            )

        self.assertIsNotNone(path)
        self.assertTrue(Path(path).exists())
        self.assertEqual(Path(path).read_bytes(), b"resume-from-gridfs")
