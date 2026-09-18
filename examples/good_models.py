from django.db import models


class Widget(models.Model):
    code = models.CharField(max_length=10, unique=True, blank=True, null=True)

    def find(self):
        return Widget.objects.filter(code__isnull=False)
