from django.urls import path

from .views import ClientFormView, ClientsListView

# URL ordering contract (plan-clients-frontend-ui.md §3.4): this include must
# stay AFTER the API include in backend/urls.py. The DRF router matches only
# numeric detail ids, so /clients/add/ and /clients/{id}/edit/ fall through
# to these patterns.
urlpatterns = [
    path("", ClientsListView.as_view(), name="clients-list-page"),
    path("clients/add/", ClientFormView.as_view(), name="client-add-page"),
    path(
        "clients/<int:client_id>/edit/",
        ClientFormView.as_view(),
        name="client-edit-page",
    ),
]
