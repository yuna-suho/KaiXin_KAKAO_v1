from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_mybox_display'),
    ]

    operations = [
        migrations.AddField(
            model_name='blacklistpolicy',
            name='mybox_page_title',
            field=models.CharField(
                blank=True,
                default='긴급 상황: 신원 확인 부탁드립니다.',
                max_length=200,
            ),
        ),
    ]
