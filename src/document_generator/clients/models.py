from django.db import models


class Client(models.Model):
    client_id = models.BigAutoField(primary_key=True)
    client_name = models.CharField(max_length=255)
    client_short_name = models.CharField(max_length=100, blank=True)
    client_industries = models.JSONField(default=list, blank=True)
    client_spoc_name = models.CharField(max_length=255)
    client_spoc_email = models.EmailField(max_length=254)
    list_of_entities = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                models.Func(models.F("client_name"), function="LOWER"),
                name="unique_client_name_ci",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.client_name
