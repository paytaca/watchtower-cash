from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied


class IsCosignerPermissionTestCase(TestCase):
    @override_settings(MULTISIG={"ENABLE_AUTH": False})
    def test_permission_disabled(self):
        from django.test import RequestFactory
        from multisig.auth.permission import IsCosigner

        permission = IsCosigner()
        factory = RequestFactory()
        request = factory.post("/")
        request.data = {"wallet": 1}
        result = permission.has_permission(request, None)
        self.assertTrue(result)
