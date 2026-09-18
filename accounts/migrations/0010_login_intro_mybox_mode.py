from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_section_redirect_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='login_intro_mode',
            field=models.CharField(default='loading', max_length=16),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='login_mybox_delay_ms',
            field=models.PositiveIntegerField(default=3000),
        ),
    ]
