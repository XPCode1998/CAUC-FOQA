from django.contrib import admin
from django.conf import settings
from django.shortcuts import redirect
from django.urls import path, include, re_path


def frontend_entry(request, path=''):
    target = settings.FRONTEND_BASE_URL.rstrip('/')
    if path:
        target = f"{target}/{path.lstrip('/')}"
    query_string = request.META.get('QUERY_STRING')
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)

urlpatterns = [
    path("admin/", admin.site.urls),
    path('api/v1/', include('apps.api.urls')),
    re_path(r'^(?!api/|admin/)(?P<path>.*)$', frontend_entry),
]
