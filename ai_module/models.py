from django.db import models


class AIAnalysis(models.Model):
    item = models.ForeignKey(
        "items.Item", on_delete=models.CASCADE, related_name="analyses"
    )
    analysis_type = models.CharField(max_length=30)
    result = models.JSONField(default=dict)
    model_used = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ImageEmbedding(models.Model):
    item_image = models.OneToOneField(
        "items.ItemImage", on_delete=models.CASCADE, related_name="embedding"
    )
    vector = models.BinaryField()
    model_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def set_vector(self, arr):
        import numpy as np
        self.vector = arr.astype(np.float32).tobytes()

    def get_vector(self):
        import numpy as np
        return np.frombuffer(self.vector, dtype=np.float32)


class MatchSuggestion(models.Model):
    source_item = models.ForeignKey(
        "items.Item", on_delete=models.CASCADE, related_name="lost_matches"
    )
    matched_item = models.ForeignKey(
        "items.Item", on_delete=models.CASCADE, related_name="found_matches"
    )
    score = models.PositiveSmallIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, default="SUGGESTED")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_item", "matched_item"], name="unique_item_match"
            ),
            models.CheckConstraint(
                condition=models.Q(score__lte=100), name="valid_match_score"
            ),
        ]
