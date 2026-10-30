from django.db import models


class TemplateMaster(models.Model):
    """Registry mapping a template name to its two on-server artifact paths.

    Paths are repo-root-relative (resolved under settings.DOCUMENTS_ROOT at
    access time) so the registry survives server moves. ``is_active`` gates
    availability everywhere (soft-delete, mirroring the clients app).
    """

    template_id = models.BigAutoField(primary_key=True)
    template_name = models.CharField(max_length=255, unique=True)
    config_path = models.CharField(max_length=500)     # e.g. "documents/config_v2.yaml"
    template_path = models.CharField(max_length=500)   # e.g. "documents/master_dpdpa_ia_v2.docx"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.template_name
