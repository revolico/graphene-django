from django import forms
from django.test import TestCase
from django.core.exceptions import ValidationError
from py.test import raises

from graphene import ObjectType, Schema, String, Field
from graphene_django import DjangoObjectType
from graphene_django.tests.models import Film, Pet

from ...settings import graphene_settings
from ..mutation import DjangoFormMutation, DjangoModelFormMutation


class MyForm(forms.Form):
    text = forms.CharField(required=False)

    def clean_text(self):
        text = self.cleaned_data["text"]
        if text == "INVALID_INPUT":
            raise ValidationError("Invalid input")
        return text

    def save(self):
        pass


class PetForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = "__all__"

    test_camel = forms.IntegerField(required=False)

    def clean_age(self):
        age = self.cleaned_data["age"]
        if age >= 99:
            raise ValidationError("Too old")
        return age


class PetType(DjangoObjectType):
    class Meta:
        model = Pet
        fields = "__all__"


class FilmType(DjangoObjectType):
    class Meta:
        model = Film
        fields = "__all__"


def test_needs_form_class():
    with raises(Exception) as exc:

        class MyMutation(DjangoFormMutation):
            pass

    assert exc.value.args[0] == "form_class is required for DjangoFormMutation"


def test_has_output_fields():
    class MyMutation(DjangoFormMutation):
        class Meta:
            form_class = MyForm

    assert "errors" in MyMutation._meta.fields


def test_has_input_fields():
    class MyMutation(DjangoFormMutation):
        class Meta:
            form_class = MyForm

    assert "text" in MyMutation.Input._meta.fields


def test_mutation_error_camelcased():
    class ExtraPetForm(PetForm):
        test_field = forms.CharField(required=True)

    class PetMutation(DjangoModelFormMutation):
        class Meta:
            form_class = ExtraPetForm

    result = PetMutation.mutate_and_get_payload(None, None)
    assert {f.field for f in result.errors} == {"name", "age", "test_field"}
    graphene_settings.CAMELCASE_ERRORS = True
    result = PetMutation.mutate_and_get_payload(None, None)
    assert {f.field for f in result.errors} == {"name", "age", "testField"}
    graphene_settings.CAMELCASE_ERRORS = False


class MockQuery(ObjectType):
    a = String()


class FormMutationTests(TestCase):
    def test_form_invalid_form(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm
                mirror_input = True

        class Mutation(ObjectType):
            my_mutation = MyMutation.Field()

        schema = Schema(query=MockQuery, mutation=Mutation)

        result = schema.execute(
            """ mutation MyMutation {
                myMutation(input: { text: "INVALID_INPUT" }) {
                    errors {
                        field
                        messages
                    }
                    text
                }
            }
            """
        )

        self.assertIs(result.errors, None)
        self.assertEqual(
            result.data["myMutation"]["errors"],
            [{"field": "text", "messages": ["Invalid input"]}],
        )

    def test_form_valid_input(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm
                mirror_input = True

        class Mutation(ObjectType):
            my_mutation = MyMutation.Field()

        schema = Schema(query=MockQuery, mutation=Mutation)

        result = schema.execute(
            """ mutation MyMutation {
                myMutation(input: { text: "VALID_INPUT" }) {
                    errors {
                        field
                        messages
                    }
                    text
                }
            }
            """
        )

        self.assertIs(result.errors, None)
        self.assertEqual(result.data["myMutation"]["errors"], [])
        self.assertEqual(result.data["myMutation"]["text"], "VALID_INPUT")

    def test_default_meta_fields(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm

        self.assertNotIn("text", MyMutation._meta.fields)

    def test_mirror_meta_fields(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm
                mirror_input = True

        self.assertIn("text", MyMutation._meta.fields)

    def test_default_input_meta_fields(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm

        self.assertIn("client_mutation_id", MyMutation.Input._meta.fields)
        self.assertIn("text", MyMutation.Input._meta.fields)

    def test_exclude_fields_input_meta_fields(self):
        class MyMutation(DjangoFormMutation):
            class Meta:
                form_class = MyForm
                exclude_fields = ["text"]

        self.assertNotIn("text", MyMutation.Input._meta.fields)
        self.assertIn("client_mutation_id", MyMutation.Input._meta.fields)


class ModelFormMutationTests(TestCase):
    def test_default_meta_fields(self):
        class PetMutation(DjangoModelFormMutation):
            class Meta:
                form_class = PetForm

        self.assertEqual(PetMutation._meta.model, Pet)
        self.assertEqual(PetMutation._meta.return_field_name, "pet")
        self.assertIn("pet", PetMutation._meta.fields)

    def test_default_input_meta_fields(self):
        class PetMutation(DjangoModelFormMutation):
            class Meta:
                form_class = PetForm

        self.assertEqual(PetMutation._meta.model, Pet)
        self.assertEqual(PetMutation._meta.return_field_name, "pet")
        self.assertIn("name", PetMutation.Input._meta.fields)
        self.assertIn("client_mutation_id", PetMutation.Input._meta.fields)
        self.assertIn("id", PetMutation.Input._meta.fields)

    def test_exclude_fields_input_meta_fields(self):
        class PetMutation(DjangoModelFormMutation):
            class Meta:
                form_class = PetForm
                exclude_fields = ["id"]

        self.assertEqual(PetMutation._meta.model, Pet)
        self.assertEqual(PetMutation._meta.return_field_name, "pet")
        self.assertIn("name", PetMutation.Input._meta.fields)
        self.assertIn("age", PetMutation.Input._meta.fields)
        self.assertIn("client_mutation_id", PetMutation.Input._meta.fields)
        self.assertNotIn("id", PetMutation.Input._meta.fields)

    def test_custom_return_field_name(self):
        class PetMutation(DjangoModelFormMutation):
            class Meta:
                form_class = PetForm
                model = Pet
                return_field_name = "animal"

        self.assertEqual(PetMutation._meta.model, Pet)
        self.assertEqual(PetMutation._meta.return_field_name, "animal")
        self.assertIn("animal", PetMutation._meta.fields)

    def test_model_form_mutation_mutate_existing(self):
        class PetMutation(DjangoModelFormMutation):
            pet = Field(PetType)

            class Meta:
                form_class = PetForm

        class Mutation(ObjectType):
            pet_mutation = PetMutation.Field()

        schema = Schema(query=MockQuery, mutation=Mutation)

        pet = Pet.objects.create(name="Axel", age=10)

        result = schema.execute(
            """ mutation PetMutation($pk: ID!) {
                petMutation(input: { id: $pk, name: "Mia", age: 10 }) {
                    pet {
                        name
                        age
                    }
                }
            }
            """,
            variable_values={"pk": pet.pk},
        )

        self.assertIs(result.errors, None)
        self.assertEqual(result.data["petMutation"]["pet"], {"name": "Mia", "age": 10})

        self.assertEqual(Pet.objects.count(), 1)
        pet.refresh_from_db()
        self.assertEqual(pet.name, "Mia")

    def test_model_form_mutation_creates_new(self):
        class PetMutation(DjangoModelFormMutation):
            pet = Field(PetType)

            class Meta:
                form_class = PetForm

        class Mutation(ObjectType):
            pet_mutation = PetMutation.Field()

        schema = Schema(query=MockQuery, mutation=Mutation)

        result = schema.execute(
            """ mutation PetMutation {
                petMutation(input: { name: "Mia", age: 10 }) {
                    pet {
                        name
                        age
                    }
                    errors {
                        field
                        messages
                    }
                }
            }
            """
        )
        self.assertIs(result.errors, None)
        self.assertEqual(result.data["petMutation"]["pet"], {"name": "Mia", "age": 10})

        self.assertEqual(Pet.objects.count(), 1)
        pet = Pet.objects.get()
        self.assertEqual(pet.name, "Mia")
        self.assertEqual(pet.age, 10)

    def test_model_form_mutation_invalid_input(self):
        class PetMutation(DjangoModelFormMutation):
            pet = Field(PetType)

            class Meta:
                form_class = PetForm

        class Mutation(ObjectType):
            pet_mutation = PetMutation.Field()

        schema = Schema(query=MockQuery, mutation=Mutation)

        result = schema.execute(
            """ mutation PetMutation {
                petMutation(input: { name: "Mia", age: 99 }) {
                    pet {
                        name
                        age
                    }
                    errors {
                        field
                        messages
                    }
                }
            }
            """
        )
        self.assertIs(result.errors, None)
        self.assertEqual(result.data["petMutation"]["pet"], None)
        self.assertEqual(
            result.data["petMutation"]["errors"],
            [{"field": "age", "messages": ["Too old"],}],
        )

        self.assertEqual(Pet.objects.count(), 0)

    def test_model_form_mutation_mutate_invalid_form(self):
        class PetMutation(DjangoModelFormMutation):
            class Meta:
                form_class = PetForm

        result = PetMutation.mutate_and_get_payload(None, None, test_camel="text")

        # A pet was not created
        self.assertEqual(Pet.objects.count(), 0)

        fields_w_error = {e.field: e.messages for e in result.errors}
        self.assertEqual(len(result.errors), 3)
        self.assertIn("test_camel", fields_w_error)
        self.assertEqual(fields_w_error["test_camel"], ["Enter a whole number."])
        self.assertIn("name", fields_w_error)
        self.assertEqual(fields_w_error["name"], ["This field is required."])
        self.assertIn("age", fields_w_error)
        self.assertEqual(fields_w_error["age"], ["This field is required."])
