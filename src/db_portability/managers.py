"""
Queryset/manager helper for fields you can't (yet) switch over to
PortableCharField/PortableTextField, but still need to query consistently
across PostgreSQL and Oracle.

Oracle treats '' and NULL as the same value for VARCHAR2/CLOB columns;
PostgreSQL does not. `.empty_or_null("field")` builds the OR'd Q object so
callers don't have to remember to write it out by hand at every call site.
"""
from django.db import models
from django.db.models import Q


def empty_or_null_q(field_name):
    return Q(**{f"{field_name}__isnull": True}) | Q(**{field_name: ""})


class PortableQuerySet(models.QuerySet):
    def empty_or_null(self, field_name):
        return self.filter(empty_or_null_q(field_name))

    def exclude_empty_or_null(self, field_name):
        return self.exclude(empty_or_null_q(field_name))


PortableManager = models.Manager.from_queryset(PortableQuerySet)
