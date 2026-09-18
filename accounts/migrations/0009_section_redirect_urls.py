from django.db import migrations, models


def copy_existing_redirects(apps, schema_editor):
    BlacklistPolicy = apps.get_model('accounts', 'BlacklistPolicy')
    for row in BlacklistPolicy.objects.all():
        url = (row.redirect_url or 'https://www.naver.com/').strip()
        row.limits_redirect_url = url
        row.login_redirect_url = url
        row.save(update_fields=['limits_redirect_url', 'login_redirect_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_myboxvisitcounter'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='limits_redirect_url',
            field=models.URLField(default='https://www.naver.com/', max_length=500),
        ),
        migrations.AddField(
            model_name='blacklistpolicy',
            name='login_redirect_url',
            field=models.URLField(default='https://www.naver.com/', max_length=500),
        ),
        migrations.RunPython(copy_existing_redirects, migrations.RunPython.noop),
    ]
