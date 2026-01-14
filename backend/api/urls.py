from django.urls import include, path
from rest_framework import routers
from api.views import (
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
    FileUpload,
    CheckIsAuthenticated,
    RandomItem,
    DeleteItem,
)

router = routers.DefaultRouter()

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("api/token", CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("api/upload", FileUpload.as_view()),
    path("api/checkauth", CheckIsAuthenticated.as_view()),
    path("api/download", RandomItem.as_view()),
    path("api/delete", DeleteItem.as_view()),
]
