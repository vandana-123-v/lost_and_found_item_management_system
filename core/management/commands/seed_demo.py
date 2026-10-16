"""Explicit, opt-in sample records for an academic demonstration."""

import getpass
import os
from datetime import timedelta
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from items.models import Item, Category
from core.services import audit
from notifications.services import notify


class Command(BaseCommand):
    help = "Create three demo accounts and labeled sample reports. Never overwrites existing accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD") or getpass.getpass(
            "Choose a strong password for the three demo accounts: "
        )
        try:
            validate_password(password)
        except Exception as exc:
            raise CommandError(
                "Choose a password that meets all password-strength rules."
            ) from exc
        usernames = ["demo.member", "demo.finder", "demo.admin"]
        if User.objects.filter(username__in=usernames).exists():
            raise CommandError("Demo accounts already exist. No records were changed.")
        users = []
        for username, name in zip(
            usernames, ["Alex Morgan", "Jamie Patel", "Community Administrator"]
        ):
            user = User.objects.create_user(
                username,
                f"{username}@example.test",
                password,
                full_name=name,
                phone="+919000000000",
                is_staff=username == "demo.admin",
            )
            users.append(user)
            notify(
                user,
                "Welcome to the demonstration",
                "These accounts and sample reports are fictional. All dashboard totals still come from database records.",
            )
            audit(user, "Demo account created", user)
        samples = [
            ("Canvas backpack", "Bags", "Sage", "Central library", "FOUND"),
            ("Wireless headphones", "Electronics", "Black", "Student lounge", "LOST"),
            ("Leather card holder", "Wallets", "Brown", "East cafeteria", "FOUND"),
            ("A set of three keys", "Keys", "Silver", "Sports complex", "FOUND"),
            ("Blue study notebook", "Books", "Blue", "Science block", "LOST"),
            (
                "Stainless steel water bottle",
                "Accessories",
                "Silver",
                "Main auditorium",
                "FOUND",
            ),
            ("Reading glasses", "Accessories", "Black", "Central library", "LOST"),
            ("Grey laptop sleeve", "Laptops", "Grey", "Computer lab", "FOUND"),
            ("Red umbrella", "Other", "Red", "West entrance", "FOUND"),
        ]
        for index, (title, category, color, location, kind) in enumerate(samples):
            category_obj, _ = Category.objects.get_or_create(name=category)
            item = Item.objects.create(
                user=users[0] if kind == "LOST" else users[1],
                item_type=kind,
                title=title,
                category=category_obj,
                primary_color=color,
                description=f"[Demonstration record] {color} {title.lower()}, reported near {location.lower()}.",
                private_identifying_details="Fictional verification mark for the academic demonstration.",
                event_date=timezone.localdate() - timedelta(days=index % 7),
                location=location,
                status="RETURNED"
                if index == 8
                else "PENDING"
                if index == 6
                else "APPROVED",
            )
            audit(
                users[2],
                "Demo report created",
                item,
                "Fictional sample data explicitly requested by seed_demo.",
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Created demo.member, demo.finder, demo.admin and 9 labeled sample reports."
            )
        )
