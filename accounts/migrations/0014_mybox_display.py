from django.db import migrations, models
import accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_blacklisthit'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_filename',
            field=models.CharField(blank=True, default='20260824_071530', max_length=120),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_filesize',
            field=models.CharField(blank=True, default='2MB', max_length=32),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_image',
            field=models.FileField(
                blank=True,
                default='',
                upload_to=accounts.models.mybox_image_upload_to,
            ),
        ),
    ]
