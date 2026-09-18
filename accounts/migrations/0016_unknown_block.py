from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_mybox_page_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='unknown_block_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='unknown_redirect_url',
            field=models.URLField(default='https://www.naver.com/', max_length=500),
        ),
    ]
