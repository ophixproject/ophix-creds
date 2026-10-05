"""
ophix_creds.views
~~~~~~~~~~~~~~~~~
API views for the Credentials domain plugin.

CredentialDetailView handles all CRUD operations on a named Credential
via a single URL pattern with method dispatch.

GET    /api/credentials/<name>/  — fetch credential (requires can_read)
POST   /api/credentials/<name>/  — create new credential (unauthenticated
                                   name check, then creates + links)
PUT    /api/credentials/<name>/  — update credential (requires can_update)
DELETE /api/credentials/<name>/  — delete credential (requires can_delete
                                   + ENABLE_ARTIFACT_DELETE setting)
"""

import logging

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

from ophix.core.auth import ClientTokenAuthentication
from ophix.core.audit import record_access
from ophix.core.utils import assert_artifact_access, err_response

from .models import Credential, ClientCredential
from .serializers import CredentialSerializer

logger = logging.getLogger(__name__)


class CredentialDetailView(APIView):
    """
    CRUD endpoint for a single named Credential.
    """

    authentication_classes = [ClientTokenAuthentication]

    # ------------------------------------------------------------------
    # GET — fetch
    # ------------------------------------------------------------------

    def get(self, request, name: str):
        client = request.user

        try:
            credential = Credential.objects.get(name=name)
        except Credential.DoesNotExist:
            raise Http404

        access = assert_artifact_access(
            client, credential, ClientCredential, "credential"
        )

        record_access(access, "GET")
        return Response(CredentialSerializer(credential).data)

    # ------------------------------------------------------------------
    # POST — create
    # ------------------------------------------------------------------

    def post(self, request, name: str):
        client = request.user

        if Credential.objects.filter(name=name).exists():
            return Response(
                {"error": err_response(str(_("Credential already exists")), str(_("Conflict")))},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = CredentialSerializer(data={**request.data, "name": name})
        serializer.is_valid(raise_exception=True)

        credential = Credential.objects.create(
            name=name,
            secret_json=serializer.validated_data["secret_json"],
            description=serializer.validated_data.get("description", ""),
        )

        # Creator gets full permissions on the new credential.
        access = ClientCredential.objects.create(
            client=client,
            credential=credential,
            enabled=True,
            can_update=True,
            can_delete=True,
            can_share=False,
        )

        record_access(access, "POST")
        return Response({"status": "created"}, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # PUT — update
    # ------------------------------------------------------------------

    def put(self, request, name: str):
        client = request.user

        try:
            credential = Credential.objects.get(name=name)
        except Credential.DoesNotExist:
            raise Http404

        assert_artifact_access(
            client, credential, ClientCredential, "credential",
            require_update=True,
        )

        serializer = CredentialSerializer(
            credential,
            data=request.data,
            partial=False,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"status": "updated"}, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(self, request, name: str):
        client = request.user

        if not getattr(settings, "ENABLE_ARTIFACT_DELETE", False):
            return Response(
                {"error": err_response(str(_("Credential deletion is disabled on this server.")))},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            credential = Credential.objects.get(name=name)
        except Credential.DoesNotExist:
            raise Http404

        assert_artifact_access(
            client, credential, ClientCredential, "credential",
            require_delete=True,
        )

        credential.delete()
        return Response({"status": "deleted"}, status=status.HTTP_200_OK)
