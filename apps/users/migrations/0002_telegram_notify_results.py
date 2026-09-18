from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="telegram_notify_results",
            field=models.BooleanField(default=True),
        ),
    ]
