from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_login_intro_mybox_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_block_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_redirect_url',
            field=models.URLField(default='https://www.naver.com/', max_length=500),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_block_empty_ua',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_block_scanner_paths',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_block_honeypot',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_block_webdriver',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_ua_keywords',
            field=models.TextField(blank=True, default=''),
        ),
    ]
