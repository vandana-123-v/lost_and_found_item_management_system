import io
import tempfile
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import User
from items.forms import ItemForm
from items.models import Category, Item, ItemImage
from items.services import save_report


def test_picture():
    stream = io.BytesIO()
    image = Image.new('RGB', (32, 32), 'white')
    for x in range(16):
        for y in range(32):
            image.putpixel((x, y), (20, 60, 100))
    image.save(stream, 'PNG')
    return SimpleUploadedFile('test.png', stream.getvalue(), content_type='image/png')


class DuplicateImageTests(TestCase):
    def test_similar_image_flags_different_title_without_deleting_reports(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            user = User.objects.create_user('reporter', 'reporter@example.test', 'Password!23')
            category, _ = Category.objects.get_or_create(name='Image test')
            item = Item.objects.create(user=user, title='Notebook', description='First report', item_type='FOUND',
                category=category, primary_color='Blue', location='Library', event_date=timezone.localdate())
            ItemImage.objects.create(item=item, image=test_picture())
            form = ItemForm({'title': 'Unidentified object', 'description': 'Different description',
                'category': category.pk, 'primary_color': 'Blue', 'location': 'Library',
                'event_date': str(timezone.localdate())}, {'images': [test_picture()]})
            self.assertTrue(form.is_valid(), form.errors)
            duplicate = save_report(form, user, 'FOUND')
            self.assertTrue(duplicate.duplicate_flag)
            self.assertEqual(Item.objects.count(), 2)
