"""
Runtime helpers for the NULL / empty-string divergence between PostgreSQL
and Oracle.

Oracle silently coerces an empty string ('') to NULL for VARCHAR2/CLOB
columns; PostgreSQL stores '' as-is. Django's own convention is "never set
null=True on CharField/TextField", which is exactly what makes the two
backends disagree: the same model, same code, same input produces a
NULL on one database and '' on the other.

These fields sidestep the disagreement by normalizing '' -> None in Python,
before the value ever reaches either database, so both backends end up
storing (and returning) the same thing. This requires null=True on the
field - that is intentional, not an oversight.
"""
from django.db import models


class PortableFieldMixin:
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value == "":
            return None
        return value

    def to_python(self, value):
        value = super().to_python(value)
        if value == "":
            return None
        return value


class PortableCharField(PortableFieldMixin, models.CharField):
    pass


class PortableTextField(PortableFieldMixin, models.TextField):
    pass
