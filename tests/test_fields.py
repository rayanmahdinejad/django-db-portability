from db_portability.fields import PortableCharField, PortableTextField


def test_char_field_normalizes_empty_string_to_none_on_prep():
    field = PortableCharField(max_length=10, null=True, blank=True)
    assert field.get_prep_value("") is None


def test_char_field_keeps_non_empty_value():
    field = PortableCharField(max_length=10, null=True, blank=True)
    assert field.get_prep_value("hello") == "hello"


def test_char_field_keeps_none():
    field = PortableCharField(max_length=10, null=True, blank=True)
    assert field.get_prep_value(None) is None


def test_char_field_to_python_normalizes_empty_string():
    field = PortableCharField(max_length=10, null=True, blank=True)
    assert field.to_python("") is None


def test_text_field_normalizes_empty_string_to_none_on_prep():
    field = PortableTextField(null=True, blank=True)
    assert field.get_prep_value("") is None
