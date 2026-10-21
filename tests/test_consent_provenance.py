from free_search.api import Consent


def test_video_frame_ocr_requires_video_consent(tmp_path):
    consent = Consent(text=True, images=True, audio_video=False, roots=(str(tmp_path),))
    assert not consent.permits({"path": str(tmp_path / "meeting.mp4"), "modality": "ocr"})


def test_scanned_pdf_ocr_requires_image_consent(tmp_path):
    consent = Consent(text=True, images=False, roots=(str(tmp_path),))
    assert not consent.permits({"path": str(tmp_path / "scan.pdf"), "modality": "ocr"})
    assert consent.permits({"path": str(tmp_path / "native.pdf"), "modality": "text"})
