import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import Clip, Job, SourceVideo, Tenant, User
from app.routers import seo
from app.services.seo_ai import SeoGenerationError
from app.services.seo_quality import QualifiedSeo


class SeoRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        tenant = Tenant(name="Test")
        self.db.add(tenant)
        self.db.flush()
        self.user = User(tenant_id=tenant.id, email="test@example.com", password_hash="unused", display_name="Test")
        self.db.add(self.user)
        self.db.flush()
        source = SourceVideo(tenant_id=tenant.id, user_id=self.user.id, youtube_id="test", title="Vendas", original_url="https://example.com")
        self.db.add(source)
        self.db.flush()
        job = Job(tenant_id=tenant.id, user_id=self.user.id, source_video_id=source.id)
        self.db.add(job)
        self.db.flush()
        subtitle = self.root / "clip.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:05,000\nUma oferta clara atrai clientes certos.", encoding="utf-8")
        self.clip = Clip(tenant_id=tenant.id, user_id=self.user.id, job_id=job.id, start_seconds=10, end_seconds=20, title="Título anterior", description="Descrição anterior", tags_json='["Anterior"]', file_path=str(self.root / "clip.mp4"), subtitle_path=str(subtitle), status="ready")
        self.db.add(self.clip)
        self.db.commit()

    def test_ai_failure_preserves_all_metadata(self):
        before = (self.clip.title, self.clip.description, self.clip.tags_json)
        with patch.object(seo, "build_ai_qualified_seo", side_effect=SeoGenerationError("IA indisponível")):
            with self.assertRaises(HTTPException) as error:
                seo.regenerate_clip_seo(self.clip.id, self.user, self.db)
        self.assertEqual(error.exception.status_code, 503)
        self.db.refresh(self.clip)
        self.assertEqual((self.clip.title, self.clip.description, self.clip.tags_json), before)

    def test_success_is_saved_and_returned(self):
        result = QualifiedSeo("Novo título sobre ofertas", "Nova descrição.", ["Ofertas", "Vendas", "Clientes"], {})
        with patch.object(seo, "build_ai_qualified_seo", return_value=result) as generate:
            response = seo.regenerate_clip_seo(self.clip.id, self.user, self.db)
        self.assertTrue(generate.call_args.kwargs["require_ai"])
        self.assertEqual(generate.call_args.kwargs["current_title"], "Título anterior")
        self.assertEqual(response["title"], result.title)
        self.assertEqual(response["tags"], result.tags)
        self.db.refresh(self.clip)
        self.assertEqual(self.clip.description, result.description)

    def test_wrong_owner_cannot_generate(self):
        other = User(id=self.user.id + 100)
        with patch.object(seo, "build_ai_qualified_seo") as generate:
            with self.assertRaises(HTTPException) as error:
                seo.regenerate_clip_seo(self.clip.id, other, self.db)
        self.assertEqual(error.exception.status_code, 404)
        generate.assert_not_called()

    def test_queued_clip_cannot_generate(self):
        self.clip.status = "upload_queued"
        self.db.commit()
        with patch.object(seo, "build_ai_qualified_seo") as generate:
            with self.assertRaises(HTTPException) as error:
                seo.regenerate_clip_seo(self.clip.id, self.user, self.db)
        self.assertEqual(error.exception.status_code, 409)
        generate.assert_not_called()

    def test_original_segments_after_removing_subtitles(self):
        self.clip.subtitle_path = ""
        self.db.commit()
        job_dir = self.root / "users" / str(self.user.id) / "jobs" / str(self.clip.job_id)
        job_dir.mkdir(parents=True)
        (job_dir / "segments.json").write_text(json.dumps([
            {"start": 0, "end": 5, "text": "Outro corte"},
            {"start": 11, "end": 18, "text": "Oferta clara e público certo."},
            {"start": 30, "end": 40, "text": "Conteúdo fora do corte"},
        ]), encoding="utf-8")
        with patch.object(settings, "data_dir", str(self.root)):
            with patch.object(seo, "build_ai_qualified_seo", side_effect=SeoGenerationError("test")) as generate:
                with self.assertRaises(HTTPException):
                    seo.regenerate_clip_seo(self.clip.id, self.user, self.db)
        self.assertEqual(generate.call_args.kwargs["content_text"], "Oferta clara e público certo.")

    def test_missing_transcript_does_not_use_previous_title(self):
        self.clip.subtitle_path = ""
        self.db.commit()
        with patch.object(settings, "data_dir", str(self.root)):
            with patch.object(seo, "build_ai_qualified_seo") as generate:
                with self.assertRaises(HTTPException) as error:
                    seo.regenerate_clip_seo(self.clip.id, self.user, self.db)
        self.assertEqual(error.exception.status_code, 422)
        generate.assert_not_called()
