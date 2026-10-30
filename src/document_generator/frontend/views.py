from django.views.generic import TemplateView


class ClientsListView(TemplateView):
    """GET / — active-clients table; rows fetched from GET /clients/ by JS."""

    template_name = "frontend/clients_list.html"


class ClientFormView(TemplateView):
    """GET /clients/add/ -> create mode; GET /clients/{id}/edit/ -> edit mode."""

    template_name = "frontend/client_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        client_id = self.kwargs.get("client_id")  # from URL converter; None on add
        ctx["mode"] = "edit" if client_id else "create"
        ctx["client_id"] = client_id
        return ctx
