from django.db import migrations

NAMES = [
    "Electronics",
    "Mobile Phones",
    "Laptops",
    "Wallets",
    "Bags",
    "Keys",
    "Documents",
    "ID Cards",
    "Books",
    "Jewellery",
    "Clothing",
    "Accessories",
    "Other",
]


def seed(apps, schema_editor):
    category = apps.get_model("items", "Category")
    for name in NAMES:
        category.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("items", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
