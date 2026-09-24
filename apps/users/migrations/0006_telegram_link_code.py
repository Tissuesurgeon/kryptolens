from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_active_lens"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="telegram_link_code",
            field=models.CharField(blank=True, max_length=16, null=True, unique=True),
        ),
    ]
