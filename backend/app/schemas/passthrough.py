"""Response models that carry the whole row, not a hand-maintained subset.

A response model that lists its fields explicitly is a second schema, kept in
step with the database by hand. It drifts, and the drift is silent: a column
added to a table simply never reaches a client, with no error anywhere to say
so.

That is not hypothetical here. The feature extractor stores its shaft-speed
estimate on every reading, and for a long time nothing downstream could see it,
because each layer between the database and the consumer carried its own list
of fields and that one was on none of them. The machine's speed appeared to be
unknown while it sat in the table the whole time.

``RowPassthrough`` closes that gap for models validated straight off an ORM
object: every mapped column is carried, declared or not. Declared fields keep
their types and validation, so an explicit field is still the way to say "this
one is a float" or "this one is optional"; the sweep only adds what nobody
thought to declare.

Two deliberate limits:

* It only fires when validating an ORM instance. A model built from keyword
  arguments in a router is unchanged, because there is no row to sweep -- the
  router decided those fields itself.
* ``NEVER_SERIALISE`` always wins. Growing the response automatically must not
  mean a new secret or a megabyte blob escapes the moment someone adds a
  column.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

#: Never sent, whatever the table gains. Two kinds: payloads that would turn a
#: single response into megabytes, and anything secret. Matched on the ORM
#: attribute name.
NEVER_SERIALISE = frozenset(
    {
        # bulk payloads
        "file_content",
        "parsed_data",
        "raw_samples",
        "samples",
        # credentials
        "password",
        "hashed_password",
        "password_hash",
        "key_hash",
        "token",
        "refresh_token",
        "secret",
    }
)

#: SQLAlchemy hangs these off every declarative class. A response model with a
#: field of the same name would otherwise be handed SQLAlchemy's own object
#: instead of the row's value -- and "metadata" is not a hypothetical clash, it
#: is a real column on the feature table. That is why columns below are swept
#: by their database name and read through their ORM attribute: the feature
#: table's "metadata" column is mapped as "metadata_" precisely to dodge this.
_ORM_INTERNALS = frozenset({"metadata", "registry"})

_MISSING = object()


class RowPassthrough(BaseModel):
    """Mixin: serialise every mapped column, not only the declared ones."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _carry_every_column(cls, data: Any) -> Any:
        mapper = getattr(type(data), "__mapper__", None)
        if mapper is None:
            # A dict or kwargs: the caller already chose the fields, and
            # sweeping would have nothing to sweep.
            return data

        carried: dict[str, Any] = {}
        for attr in mapper.column_attrs:
            # Read through the ORM attribute, publish under the database name.
            # They differ wherever a column had to be renamed to avoid clashing
            # with SQLAlchemy itself, and the database name is the one clients
            # and the rest of the schema already use.
            column = attr.columns[0] if attr.columns else None
            published = column.name if column is not None else attr.key
            if published in NEVER_SERIALISE or attr.key in NEVER_SERIALISE:
                continue
            carried[published] = getattr(data, attr.key, None)

        # Declared fields that are not plain columns -- relationships, hybrid
        # properties, anything a subclass adds. Absent attributes are left out
        # so the model's own default still applies.
        for name in cls.model_fields:
            if name in carried or name in _ORM_INTERNALS:
                continue
            value = getattr(data, name, _MISSING)
            if value is not _MISSING:
                carried[name] = value

        return carried
