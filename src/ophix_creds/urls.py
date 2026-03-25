"""
ophix_creds.urls
~~~~~~~~~~~~~~~~
URL patterns contributed by the ophix-creds plugin.
Included automatically by ophix.urls.plugins.
"""

from django.urls import path
from .views import CredentialDetailView

urlpatterns = [
    path(
        "api/credentials/<str:name>/",
        CredentialDetailView.as_view(),
        name="credential-detail",
    ),
]
