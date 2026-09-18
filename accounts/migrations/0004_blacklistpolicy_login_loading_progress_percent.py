from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_blacklistpolicy_login_intro_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='login_loading_progress_percent',
            field=models.PositiveIntegerField(default=100),
        ),
    ]
