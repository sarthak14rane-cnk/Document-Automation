from django.urls import path

from . import views

app_name = "template_master"

urlpatterns = [
    # GET  /templates/                          active templates (both files exist)
    path("templates/", views.TemplateActiveListView.as_view(), name="template-list"),
    # GET  /templates/<id>/schema/              inputs JSON structure
    path(
        "templates/<int:template_id>/schema/",
        views.TemplateSchemaView.as_view(),
        name="template-schema",
    ),
    # POST /templates/<id>/preview/             render + stream .docx
    path(
        "templates/<int:template_id>/preview/",
        views.TemplatePreviewView.as_view(),
        name="template-preview",
    ),
    # POST /ai/generate-section/                generalized AI section generation
    path("ai/generate-section/", views.AISectionView.as_view(), name="ai-section"),
]
