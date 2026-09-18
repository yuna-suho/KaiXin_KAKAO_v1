from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_blacklistpolicy_login_loading_progress_percent'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='login_loading_hold_ms',
            field=models.PositiveIntegerField(default=1000),
        ),
    ]
