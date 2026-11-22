from django.urls import path

from . import api

urlpatterns = [
    path("status/", api.RosterStatusView.as_view(), name="roster-status"),
    path("students/", api.StudentListView.as_view(), name="roster-students"),
    path(
        "students/<str:student_id>/",
        api.StudentLookupView.as_view(),
        name="roster-student",
    ),
]