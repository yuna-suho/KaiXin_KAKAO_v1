from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_remove_blacklisthit'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='bot_path_keywords',
            field=models.TextField(blank=True, default=''),
        ),
    ]
