from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_blacklistpolicy_login_loading_hold_ms'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blacklistentry',
            name='kind',
            field=models.CharField(
                choices=[
                    ('manual', 'manual'),
                    ('rate', 'rate'),
                    ('login', 'login'),
                    ('limit', 'limit'),
                    ('mybox', 'mybox'),
                ],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_visit_limit_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_visit_max',
            field=models.PositiveIntegerField(default=3),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_redirect_url',
            field=models.URLField(default='https://www.naver.com/', max_length=500),
        ),
    ]
