"""Local CLIP-based image embedding and similarity search.

Provides deterministic, server-side visual similarity using OpenCLIP
(no external API, no network calls). Embeddings are cached per ItemImage.
"""

import logging
from functools import lru_cache

import numpy as np
import open_clip
import torch
from PIL import Image, ImageOps
from django.conf import settings

from ai_module.models import ImageEmbedding

logger = logging.getLogger(__name__)

THRESHOLD = getattr(settings, "CLIP_THRESHOLD", 50)
LIMIT = 12


class CLIPError(Exception):
    """Raised when CLIP model loading or inference fails."""


@lru_cache(maxsize=1)
def _get_model():
    """Lazy-load the OpenCLIP model + preprocessing transform (cached per process)."""
    try:
        model_name = getattr(settings, "CLIP_MODEL", "ViT-B/32")
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained="openai"
        )
        model.eval()
        if not getattr(settings, "DEBUG", False):
            torch.set_grad_enabled(False)
        return model, preprocess
    except Exception as exc:
        logger.error("Failed to load CLIP model: %s", exc)
        raise CLIPError(f"CLIP model '{model_name}' could not be loaded") from exc


def _preprocess_image(image_file):
    """Open a Django file-like or storage-backed image and run CLIP preprocessing.

    Strips EXIF orientation, converts to RGB, and returns a (1, C, H, W) tensor.
    Handles both Django storage-backed files (which need .open()) and raw
    file-like objects (BytesIO, UploadedFile).
    """
    is_storage = hasattr(image_file, "storage")
    opened_here = False
    try:
        if is_storage:
            image_file.open("rb")
            opened_here = True
        else:
            image_file.seek(0)
        with Image.open(image_file) as source:
            img = ImageOps.exif_transpose(source).convert("RGB")
            tensor = _preprocess(img).unsqueeze(0)
        return tensor
    except (OSError, ValueError) as exc:
        raise CLIPError("Image could not be read") from exc
    finally:
        if opened_here:
            image_file.close()
        else:
            image_file.seek(0)


def _preprocess(img: Image.Image):
    """Wrapper around the CLIP preprocess transform for PIL Images."""
    model, preprocess = _get_model()
    return preprocess(img)


def compute_embedding(image_field) -> np.ndarray:
    """Compute and return a normalized 512-dim (ViT-B/32) embedding for one image.

    Returns a float32 numpy array, L2-normalized.
    """
    model, _ = _get_model()
    tensor = _preprocess_image(image_field)
    with torch.inference_mode():
        embedding = model.encode_image(tensor)
    embedding = embedding / embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze().numpy().astype(np.float32)


def store_embedding(item_image) -> "ImageEmbedding":
    """Compute the CLIP embedding for an ItemImage and persist it."""
    vec = compute_embedding(item_image.image)
    model_name = getattr(settings, "CLIP_MODEL", "ViT-B/32")
    emb, created = ImageEmbedding.objects.update_or_create(
        item_image=item_image,
        defaults={"model_name": model_name},
    )
    emb.set_vector(vec)
    emb.save(update_fields=["vector", "model_name"])
    return emb


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for L2-normalized vectors = dot product."""
    return float(np.dot(a, b))


def similarity_to_score(sim: float) -> int:
    """Map cosine similarity [-1, 1] to a 0-100 integer score."""
    normalized = (sim + 1.0) / 2.0  # [-1,1] -> [0,1]
    normalized = max(0.0, min(1.0, normalized))
    return round(normalized * 100)


def _query_embedding_from_upload(upload_file) -> np.ndarray:
    """Compute the L2-normalized embedding for an uploaded search photo."""
    model, _ = _get_model()
    tensor = _preprocess_image(upload_file)
    with torch.inference_mode():
        embedding = model.encode_image(tensor)
    embedding = embedding / embedding.norm(dim=-1, keepdim=True)
    return embedding.squeeze().numpy().astype(np.float32)


def available(user):
    """Return the candidate pool — found, approved/matched items with images, excluding user's own."""
    from items.models import Item

    return (
        Item.objects.filter(
            item_type="FOUND",
            status__in=["APPROVED", "MATCHED"],
            images__isnull=False,
        )
        .exclude(user=user)
        .distinct()
    )


def compute_image_embedding(item):
    """Compute and store CLIP embeddings for all images of an approved item."""
    if not getattr(settings, "CLIP_ENABLED", False):
        return False
    try:
        for img in item.images.all():
            store_embedding(img)
        return True
    except Exception:
        logger.warning("CLIP embedding failed for item %s; retained.", item.pk)
        return False


def similarity_between(query_vec: np.ndarray, candidate_vec: np.ndarray) -> int:
    """Return 0-100 similarity score between two L2-normalized embeddings."""
    score = similarity_to_score(cosine_similarity(query_vec, candidate_vec))
    return score


def clip_image_search(user, upload, category=None, location=""):
    """Pure CLIP-based image search over the candidate pool.

    Returns the same result dict shape as image_search.search_by_image:
        {"results": [...], "compared": int, "eligible": int, "features": None}
    """
    pool = available(user)
    if category:
        pool = pool.filter(category=category)
    if location:
        pool = pool.filter(location__icontains=location)

    total_eligible = pool.count()
    if not total_eligible:
        return {"results": [], "compared": 0, "eligible": 0, "features": None}

    query_vec = _query_embedding_from_upload(upload)

    candidates = list(
        pool.select_related("category")
        .prefetch_related("images")[:LIMIT]
    )

    candidate_embs = []
    candidate_items = []
    for item in candidates:
        try:
            emb = ImageEmbedding.objects.get(item_image=item.images.first())
            candidate_embs.append(emb.get_vector())
            candidate_items.append(item)
        except ImageEmbedding.DoesNotExist:
            continue
        except Exception:
            continue

    if not candidate_embs:
        raise CLIPError("No item images have embeddings computed yet.")

    matrix = np.stack(candidate_embs)
    scores = (matrix @ query_vec).flatten()

    results = []
    compared = len(candidate_items)
    for idx, item in enumerate(candidate_items):
        score = similarity_to_score(float(scores[idx]))
        if score >= THRESHOLD:
            results.append(
                {
                    "item": item,
                    "score": score,
                    "reason": f"CLIP visual similarity ({score}%). Model: {getattr(settings, 'CLIP_MODEL', 'ViT-B/32')}. "
                              f"Embedding-based comparison is deterministic; "
                              f"visual similarity does not prove ownership.",
                }
            )
    results.sort(key=lambda row: (-row["score"], row["item"].pk))

    return {
        "results": results,
        "compared": compared,
        "eligible": total_eligible,
        "features": None,
    }