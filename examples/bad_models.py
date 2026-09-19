from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.aggregates import ArrayAgg


class Widget(models.Model):
    tags = ArrayField(models.CharField(max_length=20))
    code = models.CharField(max_length=10, unique=True, blank=True)

    def find(self):
        return Widget.objects.extra(where=["1=1"])

    def raw_query(self, cursor):
        cursor.execute("SELECT * FROM widget WHERE name ILIKE 'a%'")

    def unique_names(self):
        return Widget.objects.order_by("name").distinct("name")
