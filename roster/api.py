from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .identity import id_problem, normalize_id
from .models import Student, SyncLog


def current_term():
    return getattr(settings, "ROSTER_CURRENT_TERM", "FA26")


def stale_after_hours():
    return getattr(settings, "ROSTER_STALE_AFTER_HOURS", 24)


def freshness():
    """How old the roster data is, based on the last successful sync."""
    last = (
        SyncLog.objects.filter(
            status=SyncLog.Status.SUCCESS, finished_at__isnull=False
        )
        .order_by("-finished_at")
        .first()
    )
    limit = stale_after_hours()
    if last is None:
        return {
            "last_successful_sync_at": None,
            "age_hours": None,
            "stale": True,
            "stale_after_hours": limit,
        }
    age = (timezone.now() - last.finished_at).total_seconds() / 3600
    return {
        "last_successful_sync_at": last.finished_at,
        "age_hours": round(age, 2),
        "stale": age > limit,
        "stale_after_hours": limit,
    }


def stale_warning(fresh):
    if not fresh["stale"]:
        return None
    if fresh["last_successful_sync_at"] is None:
        return (
            "The roster has never been synced successfully. "
            "Treat these results as unreliable."
        )
    return (
        f"The roster was last synced successfully {fresh['age_hours']:.0f} hours ago "
        f"(limit {fresh['stale_after_hours']}). Results may be out of date."
    )


def explain(student, term):
    """Return (eligible, reason) for a student on the roster."""
    if student.status == Student.Status.ACTIVE:
        if student.term == term:
            return True, f"Active on the {term} roster."
        return False, (
            f"On the roster for {student.term}, not the current term ({term})."
        )
    if student.status == Student.Status.INACTIVE:
        when = student.last_synced_at.strftime("%Y-%m-%d %H:%M UTC")
        return False, (
            "Not enrolled according to the latest sync. "
            f"Last confirmed enrolled: {when}."
        )
    return False, (
        "Held for administrator review. An administrator needs to confirm "
        "this student."
    )


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            "panthersoft_id", "first_name", "last_name",
            "email", "term", "status", "last_synced_at",
        )


class RosterPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["current_term"] = current_term()
        response.data["data_freshness"] = freshness()
        return response


class RosterStatusView(APIView):
    """Is the roster fresh, and how did the latest sync go?"""

    def get(self, request):
        term = current_term()
        latest = SyncLog.objects.order_by("-started_at").first()
        latest_sync = None
        if latest:
            latest_sync = {
                "status": latest.status,
                "started_at": latest.started_at,
                "finished_at": latest.finished_at,
                "added": latest.added,
                "updated": latest.updated,
                "deactivated": latest.deactivated,
                "set_aside_records": latest.issues.count(),
                "message": latest.error_message,
            }
        counts = {
            value: Student.objects.filter(term=term, status=value).count()
            for value in Student.Status.values
        }
        return Response({
            "current_term": term,
            "data_freshness": freshness(),
            "latest_sync": latest_sync,
            "students_in_current_term": counts,
        })


class StudentLookupView(APIView):
    """Is this ID on the active roster, and if not, why not?"""

    def get(self, request, student_id):
        term = current_term()
        fresh = freshness()
        sid = normalize_id(student_id)  # same rules the sync uses
        body = {
            "queried_id": sid[:50],
            "eligible": False,
            "current_term": term,
            "warning": stale_warning(fresh),
            "data_freshness": fresh,
        }

        problem = id_problem(sid) if sid else "The ID is blank"
        if problem:
            body.update(
                status="invalid_id",
                reason=(
                    f"{problem}. This is a problem with the ID that was sent, "
                    "not evidence that the student is missing."
                ),
            )
            return Response(body, status=http.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(panthersoft_id=sid).first()
        if student is None:
            body.update(
                status="not_found",
                reason="No student with this ID is on the roster.",
            )
            return Response(body, status=http.HTTP_404_NOT_FOUND)

        eligible, reason = explain(student, term)
        body.update(
            status=student.status,
            eligible=eligible,
            reason=reason,
            student=StudentSerializer(student).data,
        )
        return Response(body)


class StudentListView(ListAPIView):
    """The roster for a term, filterable by status and paginated."""

    serializer_class = StudentSerializer
    pagination_class = RosterPagination

    def get_queryset(self):
        params = self.request.query_params
        queryset = Student.objects.filter(term=params.get("term") or current_term())
        wanted = params.get("status")
        if wanted:
            if wanted not in Student.Status.values:
                raise ValidationError({
                    "status": f"Must be one of: {', '.join(Student.Status.values)}"
                })
            queryset = queryset.filter(status=wanted)
        return queryset.order_by("last_name", "first_name", "panthersoft_id")