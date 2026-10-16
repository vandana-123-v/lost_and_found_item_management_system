from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from items.models import Category, Item


@override_settings(SECURE_SSL_REDIRECT=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReportDateTests(TestCase):
    def test_local_calendar_date_filter_without_mysql_timezone_tables(self):
        admin = User.objects.create_user('admin', 'admin@example.test', 'Password!23', is_staff=True)
        category, _ = Category.objects.get_or_create(name='Date test')
        item = Item.objects.create(user=admin, item_type='LOST', title='Date-filtered item',
            description='Date filtering test', category=category, primary_color='Blue',
            location='Office', event_date=timezone.localdate())
        self.client.force_login(admin)
        today = str(timezone.localdate())
        response = self.client.get(reverse('reports'), {'from': today, 'to': today, 'export': 'csv'})
        self.assertContains(response, item.title)
        tomorrow = str(timezone.localdate() + timedelta(days=1))
        response = self.client.get(reverse('reports'), {'from': tomorrow, 'export': 'csv'})
        self.assertNotContains(response, item.title)
