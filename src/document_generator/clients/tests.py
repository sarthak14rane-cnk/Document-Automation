"""API tests for the Clients CRUD endpoints.

Run with:  uv run python manage.py test clients
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from clients.models import Client


class ClientCRUDTests(APITestCase):
    """Full CRUD matrix per docs/plan-clients-app-crud.md (§4 Testing strategy)."""

    LIST_URL = reverse("client-list")

    def _payload(self, **overrides):
        data = {
            "client_name": "Acme Ltd",
            "client_short_name": "Acme",
            "client_industries": ["Manufacturing", "FMCG"],
            "client_spoc_name": "Priya Sharma",
            "client_spoc_email": "priya@acme.com",
            "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"],
        }
        data.update(overrides)
        return data

    # ---- Create (POST /clients/) ----

    def test_create_valid_payload_returns_201(self):
        response = self.client.post(self.LIST_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        body = response.json()
        self.assertIn("client_id", body)
        self.assertNotIn("id", body)
        self.assertTrue(body["is_active"])
        self.assertIsNotNone(body["created_at"])
        self.assertIsNotNone(body["updated_at"])
        self.assertEqual(Client.objects.count(), 1)

    def test_create_duplicate_name_exact_returns_409(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        response = self.client.post(self.LIST_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.content)

    def test_create_duplicate_name_case_insensitive_returns_409(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        response = self.client.post(
            self.LIST_URL, self._payload(client_name="ACME LTD"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.content)

    def test_create_missing_required_fields_returns_400(self):
        response = self.client.post(
            self.LIST_URL,
            {"client_name": "Acme Ltd"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("client_spoc_name", response.json())
        self.assertIn("client_spoc_email", response.json())

    def test_create_invalid_email_returns_400(self):
        response = self.client.post(
            self.LIST_URL,
            self._payload(client_spoc_email="not-an-email"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("client_spoc_email", response.json())

    def test_create_industries_must_be_list_of_strings(self):
        # string instead of list
        response = self.client.post(
            self.LIST_URL, self._payload(client_industries="Manufacturing"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)

        # list with non-string member
        response = self.client.post(
            self.LIST_URL, self._payload(client_industries=["Manufacturing", 42]), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)

        # empty list is OK
        response = self.client.post(
            self.LIST_URL, self._payload(client_industries=[]), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

    def test_create_readonly_fields_ignored(self):
        response = self.client.post(
            self.LIST_URL,
            self._payload(client_id=999, is_active=False),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        client = Client.objects.get()
        self.assertEqual(client.client_id, 1)
        self.assertTrue(client.is_active)

    def test_create_without_optional_fields_returns_201(self):
        """Regression (D1): omitted client_short_name must become "", not NULL.

        Previously POST with only the required keys crashed with a 500
        IntegrityError (NotNullViolation on client_short_name).
        """
        response = self.client.post(
            self.LIST_URL,
            {
                "client_name": "Alpha Ltd",
                "client_spoc_name": "Priya Sharma",
                "client_spoc_email": "priya@alpha.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        client = Client.objects.get()
        self.assertEqual(client.client_short_name, "")
        self.assertEqual(client.client_industries, [])
        self.assertEqual(client.list_of_entities, [])

    def test_create_null_list_fields_coerced_to_empty(self):
        """Regression (D2): explicit null for list fields coerces to [] (plan §3.4).

        Previously POST with client_industries/list_of_entities = null returned
        400 "This field may not be null."
        """
        response = self.client.post(
            self.LIST_URL,
            self._payload(client_industries=None, list_of_entities=None),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        client = Client.objects.get()
        self.assertEqual(client.client_industries, [])
        self.assertEqual(client.list_of_entities, [])

    # ---- Read (GET) ----

    def test_list_returns_active_only_newest_first(self):
        self.client.post(self.LIST_URL, self._payload(client_name="First"), format="json")
        self.client.post(
            self.LIST_URL, self._payload(client_name="Second"), format="json"
        )
        # soft-delete the first one
        Client.objects.filter(client_name="First").update(is_active=False)

        response = self.client.get(self.LIST_URL, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        names = [item["client_name"] for item in response.json()]
        self.assertEqual(names, ["Second"])

    def test_retrieve_active_client_returns_200_with_all_fields(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        response = self.client.get(
            reverse("client-detail", kwargs={"client_id": client.client_id}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        body = response.json()
        expected_keys = {
            "client_id",
            "client_name",
            "client_short_name",
            "client_industries",
            "client_spoc_name",
            "client_spoc_email",
            "list_of_entities",
            "is_active",
            "created_at",
            "updated_at",
        }
        self.assertEqual(set(body.keys()), expected_keys)

    def test_retrieve_inactive_unknown_nonnumeric_id_all_404(self):
        active = self.client.post(self.LIST_URL, self._payload(), format="json").json()
        inactive = Client.objects.create(
            client_name="Inactive Co",
            client_spoc_name="X",
            client_spoc_email="x@example.com",
        )
        inactive.is_active = False
        inactive.save()

        response = self.client.get(
            reverse("client-detail", kwargs={"client_id": inactive.client_id}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

        response = self.client.get(
            reverse("client-detail", kwargs={"client_id": 999999}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

        response = self.client.get("/clients/abc/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

    # ---- Update (PUT) ----

    def test_put_full_update_returns_200(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            self._payload(client_name="Acme Corp"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        client.refresh_from_db()
        self.assertEqual(client.client_name, "Acme Corp")
        self.assertGreater(client.updated_at, client.created_at)

    def test_put_missing_key_returns_400(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        data = self._payload()
        del data["list_of_entities"]
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("list_of_entities", response.json())

    def test_put_rename_to_other_client_name_case_variant_409(self):
        self.client.post(self.LIST_URL, self._payload(client_name="Beta"), format="json")
        self.client.post(self.LIST_URL, self._payload(client_name="Alpha"), format="json")
        alpha = Client.objects.get(client_name="Alpha")
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": alpha.client_id}),
            self._payload(client_name="BETA"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.content)

    def test_put_rename_to_own_name_case_variant_200(self):
        self.client.post(self.LIST_URL, self._payload(client_name="Gamma"), format="json")
        client = Client.objects.get(client_name="Gamma")
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            self._payload(client_name="GAMMA"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

    def test_put_inactive_client_returns_404(self):
        client = Client.objects.create(
            client_name="Inactive Co",
            client_short_name="Inactive",
            client_industries=["X"],
            client_spoc_name="Y",
            client_spoc_email="y@example.com",
            list_of_entities=["Z"],
            is_active=False,
        )
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            self._payload(client_name="Changed"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

    def test_put_ignores_readonly_fields(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        data = self._payload()
        data.update(client_id=999, is_active=False)
        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        client.refresh_from_db()
        self.assertEqual(client.client_id, client.pk)
        self.assertTrue(client.is_active)

    def test_patch_disabled_returns_405(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        response = self.client.patch(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            {"client_short_name": "New"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, response.content)

    # ---- Delete (DELETE) ----

    def test_delete_soft_deletes_returns_204(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        response = self.client.delete(
            reverse("client-detail", kwargs={"client_id": client.client_id}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.content)
        self.assertEqual(response.content, b"")
        client.refresh_from_db()
        self.assertFalse(client.is_active)

    def test_deleted_client_excluded_from_everywhere(self):
        self.client.post(self.LIST_URL, self._payload(), format="json")
        client = Client.objects.get()
        self.client.delete(
            reverse("client-detail", kwargs={"client_id": client.client_id}), format="json"
        )

        response = self.client.get(self.LIST_URL, format="json")
        self.assertEqual(response.json(), [])

        response = self.client.get(
            reverse("client-detail", kwargs={"client_id": client.client_id}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

        response = self.client.put(
            reverse("client-detail", kwargs={"client_id": client.client_id}),
            self._payload(client_name="Changed"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

    def test_delete_second_time_and_unknown_id_404(self):
        response = self.client.delete(
            reverse("client-detail", kwargs={"client_id": 999999}), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)
