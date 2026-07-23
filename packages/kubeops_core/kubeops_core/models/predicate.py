from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import Field

from .base import SchemaModel


class FieldEquals(SchemaModel):
    kind: ClassVar[str] = "FieldEquals"
    predicate_type: Literal["field_equals"] = "field_equals"
    entity_id: str
    path: str
    value: Any


class FieldNotEquals(SchemaModel):
    kind: ClassVar[str] = "FieldNotEquals"
    predicate_type: Literal["field_not_equals"] = "field_not_equals"
    entity_id: str
    path: str
    value: Any


class FieldExists(SchemaModel):
    kind: ClassVar[str] = "FieldExists"
    predicate_type: Literal["field_exists"] = "field_exists"
    entity_id: str
    path: str
    expected: bool = True


class FieldGte(SchemaModel):
    kind: ClassVar[str] = "FieldGte"
    predicate_type: Literal["field_gte"] = "field_gte"
    entity_id: str
    path: str
    value: float


class FieldLte(SchemaModel):
    kind: ClassVar[str] = "FieldLte"
    predicate_type: Literal["field_lte"] = "field_lte"
    entity_id: str
    path: str
    value: float


class AllOfPredicate(SchemaModel):
    kind: ClassVar[str] = "AllOfPredicate"
    predicate_type: Literal["all_of"] = "all_of"
    predicates: list["Predicate"] = Field(min_length=1)


class AnyOfPredicate(SchemaModel):
    kind: ClassVar[str] = "AnyOfPredicate"
    predicate_type: Literal["any_of"] = "any_of"
    predicates: list["Predicate"] = Field(min_length=1)


class NotPredicate(SchemaModel):
    kind: ClassVar[str] = "NotPredicate"
    predicate_type: Literal["not"] = "not"
    predicate: "Predicate"


Predicate = Annotated[
    Union[
        FieldEquals,
        FieldNotEquals,
        FieldExists,
        FieldGte,
        FieldLte,
        AllOfPredicate,
        AnyOfPredicate,
        NotPredicate,
    ],
    Field(discriminator="predicate_type"),
]

AllOfPredicate.model_rebuild()
AnyOfPredicate.model_rebuild()
NotPredicate.model_rebuild()
