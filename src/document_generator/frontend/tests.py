"""Page-level smoke tests for the frontend app (views, URLs and templates).

These tests render template-only pages — no database access. The client-data
binding itself lives in frontend/static JS (manual browser matrix in the
plan) and the API regression suite lives in clients/tests.py.
"""

from django.test import TestCase

FORM_FIELD_NAMES = (
    "client_name",
    "client_short_name",
    "client_industries",
    "client_spoc_name",
    "client_spoc_email",
    "list_of_entities",
)


class ClientsListPageTests(TestCase):
    def test_home_page_renders_clients_list(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/clients_list.html")

    def test_home_page_shows_heading_and_columns(self):
        response = self.client.get("/")
        self.assertContains(response, "<h1", status_code=200)
        self.assertContains(response, "Client Name")
        self.assertContains(response, "Short Name")
        self.assertContains(response, "SPOC Name")

    def test_home_page_links_to_add_client_page(self):
        response = self.client.get("/")
        self.assertContains(response, "+ Add Client")
        self.assertContains(response, "/clients/add/")

    def test_home_page_includes_list_script(self):
        response = self.client.get("/")
        self.assertContains(response, "frontend/js/clients.js")


class ClientFormPageTests(TestCase):
    """Add + edit pages share one template, driven by mode."""

    def test_add_page_renders_form_template(self):
        response = self.client.get("/clients/add/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/client_form.html")
        self.assertContains(response, "Add New Client")

    def test_add_page_has_all_registration_fields(self):
        response = self.client.get("/clients/add/")
        for name in FORM_FIELD_NAMES:
            self.assertContains(response, f'name="{name}"')

    def test_add_page_declares_create_mode(self):
        response = self.client.get("/clients/add/")
        self.assertContains(response, 'data-mode="create"')
        self.assertNotContains(response, 'data-mode="edit"')

    def test_edit_page_renders_edit_mode(self):
        response = self.client.get("/clients/1/edit/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/client_form.html")
        self.assertContains(response, "Edit Client")

    def test_edit_page_declares_edit_mode_with_client_id(self):
        response = self.client.get("/clients/1/edit/")
        self.assertContains(response, 'data-mode="edit"')
        self.assertContains(response, 'data-client-id="1"')

    def test_edit_page_url_requires_numeric_client_id(self):
        response = self.client.get("/clients/abc/edit/")
        self.assertEqual(response.status_code, 404)
