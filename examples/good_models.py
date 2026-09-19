from django.db import models
from django.db.models import Count


class Widget(models.Model):
    code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    label = models.CharField(max_length=150, null=True)

    def find(self):
        return Widget.objects.filter(code__isnull=False)

    def part_counts(self):
        return Widget.objects.annotate(part_count=Count("parts", distinct=True))

    def with_latest_note(self):
        # Keep the aggregate and the per-row Subquery in separate queries -
        # e.g. attach latest_note in Python after fetching, or via a
        # separate .annotate() pass consumed independently - rather than
        # combining both in the same annotate() call/GROUP BY.
        return Widget.objects.annotate(part_count=Count("parts", distinct=True))
