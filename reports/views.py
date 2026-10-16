import csv
from datetime import date, datetime, time, timedelta
from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import render
from core.services import staff_required, audit
from items.models import Item, Category
from claims.models import Claim
from accounts.models import User
from ai_module.models import MatchSuggestion
from dashboard.services import statistics, chart_data


def safe_cell(value):
    value = str(value)
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
    )


@staff_required
def report(request):
    items = Item.objects.select_related("category")
    claims = Claim.objects.all()
    users = User.objects.all()
    matches = MatchSuggestion.objects.all()
    errors = []
    for key, lookup in [("from", "created_at__gte"), ("to", "created_at__lt")]:
        if request.GET.get(key):
            try:
                day = date.fromisoformat(request.GET[key])
                if key == "to":
                    day += timedelta(days=1)
                value = timezone.make_aware(datetime.combine(day, time.min))
                items, claims, users, matches = [
                    qs.filter(
                        **{
                            lookup
                            if qs.model != User
                            else lookup.replace("created_at", "date_joined"): value
                        }
                    )
                    for qs in [items, claims, users, matches]
                ]
            except ValueError:
                errors.append("Use valid dates in YYYY-MM-DD format.")
    if request.GET.get("category", "").isdigit():
        category = request.GET["category"]
        items = items.filter(category_id=category)
        claims = claims.filter(item__category_id=category)
        matches = matches.filter(source_item__category_id=category)
    if request.GET.get("status"):
        items = items.filter(status=request.GET["status"])
        claims = claims.filter(item__status=request.GET["status"])
        matches = matches.filter(source_item__status=request.GET["status"])
    stats = statistics(items=items, claims=claims)
    stats["Suggested matches"] = matches.count()
    stats.update(
        {
            "Total users": users.count(),
            "Total claims": claims.count(),
            "Pending claims": claims.filter(
                status__in=["PENDING", "UNDER_REVIEW"]
            ).count(),
            "Approved claims": claims.filter(status="APPROVED").count(),
            "Rejected claims": claims.filter(status="REJECTED").count(),
        }
    )
    total = items.count()
    stats["Recovery rate (%)"] = (
        round(items.filter(status="RETURNED").count() * 100 / total, 1) if total else 0
    )
    charts = chart_data(items, claims)
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="lost-found-report.csv"'
        writer = csv.writer(response)
        writer.writerow(["Metric", "Value"])
        writer.writerows(stats.items())
        for section, rows in charts.items():
            writer.writerow([])
            writer.writerow([section])
            if rows:
                writer.writerow(rows[0].keys())
                writer.writerows([[safe_cell(v) for v in row.values()] for row in rows])
        writer.writerow([])
        writer.writerow(
            ["ID", "Type", "Title", "Category", "Status", "Event date", "Location"]
        )
        for item in items.iterator():
            writer.writerow(
                [
                    safe_cell(v)
                    for v in [
                        item.pk,
                        item.item_type,
                        item.title,
                        item.category,
                        item.status,
                        item.event_date,
                        item.location,
                    ]
                ]
            )
        audit(request.user, "Admin CSV exported", description="Filtered system report")
        return response
    return render(
        request,
        "admin_panel/reports.html",
        {
            "title": "Reports & insights",
            "stats": stats,
            "charts": charts,
            "categories": Category.objects.all(),
            "statuses": Item.STATUSES,
            "errors": errors,
        },
    )
