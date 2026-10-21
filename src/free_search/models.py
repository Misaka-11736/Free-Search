"""Local-only model inference. Downloading models is a separate build operation."""
from __future__ import annotations

import gc
import importlib.util
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

# Set before importing the HF stack. Every loader also receives a real local path.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"


class ModelUnavailable(RuntimeError):
    """An explicitly named local model or inference dependency is missing."""


class LocalModels:
    """Reuse local CPU models across files to avoid repeated weight loading."""

    TEXT_DIM = 384
    VISION_DIM = 512

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir).resolve()
        self._active = None
        self._active_name = None
        self._ocr = None
        self._cache = {}

    def _path(self, name: str) -> Path:
        path = self.model_dir / name
        if not path.is_dir():
            raise ModelUnavailable(f"缺少本地模型：{path}。请安装模型包；程序不会自动联网下载。")
        return path

    def availability(self) -> dict[str, bool]:
        def package(name):
            return importlib.util.find_spec(name) is not None

        def weights(name):
            directory = self.model_dir / name
            return any(directory.glob("*.safetensors")) or any(directory.glob("*.bin"))

        torch_ready = package("torch") and package("transformers")
        return {
            "text_embedding": torch_ready and weights("text-embedding"),
            "text_reranker": torch_ready and weights("text-reranker"),
            "vision": torch_ready and weights("vision"),
            "speech": package("faster_whisper") and (self.model_dir / "speech/model.bin").is_file(),
            "ocr": package("rapidocr_onnxruntime"),
        }

    def _load(self, name):
        if self._active_name == name:
            return self._active
        if name in self._cache:
            self._active_name = name
            self._active = self._cache[name]
            return self._active
        path = self._path(name)
        self._active = None
        self._active_name = None
        gc.collect()
        try:
            if name == "speech":
                from faster_whisper import WhisperModel

                model = WhisperModel(str(path), device="cpu", compute_type="int8",
                                     cpu_threads=4, local_files_only=True)
                active = model
            else:
                import torch
                from transformers import (
                    AutoModel, AutoModelForSequenceClassification, AutoTokenizer,
                    ChineseCLIPModel, ChineseCLIPProcessor,
                )

                torch.set_num_threads(4)
                if name == "vision":
                    processor = ChineseCLIPProcessor.from_pretrained(str(path), local_files_only=True)
                    model = ChineseCLIPModel.from_pretrained(str(path), local_files_only=True)
                else:
                    processor = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
                    loader = AutoModel if name == "text-embedding" else AutoModelForSequenceClassification
                    model = loader.from_pretrained(str(path), local_files_only=True)
                model.eval()
                active = (processor, model)
        except (ImportError, OSError) as exc:
            raise ModelUnavailable(f"本地模型 {name} 加载失败：{exc}") from exc
        self._active = active
        self._active_name = name
        self._cache[name] = active
        return active

    def _text(self, texts: list[str], prefix: str) -> np.ndarray:
        import numpy as np
        import torch

        if not texts:
            return np.empty((0, self.TEXT_DIM), dtype=np.float32)
        tokenizer, model = self._load("text-embedding")
        result = []
        for offset in range(0, len(texts), 8):
            encoded = tokenizer([prefix + t for t in texts[offset:offset + 8]],
                                max_length=512, padding=True, truncation=True, return_tensors="pt")
            with torch.inference_mode():
                hidden = model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).bool()
                pooled = hidden.masked_fill(~mask, 0.0).sum(dim=1) / mask.sum(dim=1)
                result.append(torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().numpy())
        return np.concatenate(result).astype(np.float32)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        return self._text(texts, "passage: ")

    def embed_query(self, query: str) -> np.ndarray:
        return self._text([query], "query: ")[0]

    def embed_vision_text(self, texts: list[str]) -> np.ndarray:
        import numpy as np
        import torch

        if not texts:
            return np.empty((0, self.VISION_DIM), dtype=np.float32)
        processor, model = self._load("vision")
        outputs = []
        for offset in range(0, len(texts), 8):
            encoded = processor(text=texts[offset:offset + 8], return_tensors="pt",
                                padding=True, truncation=True, max_length=52)
            with torch.inference_mode():
                vectors = model.get_text_features(**encoded).pooler_output
                outputs.append(torch.nn.functional.normalize(vectors, p=2, dim=1).cpu().numpy())
        return np.concatenate(outputs).astype(np.float32)

    def embed_images(self, paths: list[str]) -> np.ndarray:
        import numpy as np
        import torch
        from PIL import Image, ImageOps

        if not paths:
            return np.empty((0, self.VISION_DIM), dtype=np.float32)
        processor, model = self._load("vision")
        outputs = []
        for offset in range(0, len(paths), 4):
            images = []
            try:
                for path in paths[offset:offset + 4]:
                    with Image.open(path) as source:
                        images.append(ImageOps.exif_transpose(source).convert("RGB"))
                encoded = processor(images=images, return_tensors="pt")
                with torch.inference_mode():
                    vectors = model.get_image_features(**encoded).pooler_output
                    outputs.append(torch.nn.functional.normalize(vectors, p=2, dim=1).cpu().numpy())
            finally:
                for image in images:
                    image.close()
        return np.concatenate(outputs).astype(np.float32)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        import torch

        if not texts:
            return []
        tokenizer, model = self._load("text-reranker")
        scores = []
        for offset in range(0, len(texts), 4):
            pairs = [(query, text) for text in texts[offset:offset + 4]]
            encoded = tokenizer(pairs, max_length=512, padding=True, truncation=True,
                                return_tensors="pt")
            with torch.inference_mode():
                scores.extend(model(**encoded).logits.flatten().float().tolist())
        return scores

    def transcribe(self, path) -> list[dict]:
        import av
        import numpy as np

        model = self._load("speech")
        # Decode explicitly: PyAV 19 removed metadata_errors used by older Whisper helpers.
        samples = []
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with av.open(str(path)) as container:
            for frame in container.decode(audio=0):
                samples.extend(out.to_ndarray().flatten() for out in resampler.resample(frame))
            samples.extend(out.to_ndarray().flatten() for out in resampler.resample(None))
        if not samples:
            return []
        audio = np.concatenate(samples).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio, beam_size=3, vad_filter=True)
        return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments
                if s.text.strip()]

    def ocr(self, path) -> str:
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise ModelUnavailable("缺少本地 OCR 组件 rapidocr-onnxruntime。") from exc
            # This distribution includes its three ONNX models; no download occurs.
            self._ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        # Reading bytes handles non-ASCII Windows paths consistently.
        result, _ = self._ocr(Path(path).read_bytes())
        return "\n".join(str(row[1]) for row in (result or []))
