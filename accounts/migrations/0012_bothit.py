from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_bot_block'),
    ]

    operations = [
        migrations.CreateModel(
            name='BotHit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip', models.CharField(db_index=True, max_length=45)),
                ('reason', models.CharField(blank=True, default='', max_length=32)),
                ('path', models.CharField(blank=True, default='', max_length=500)),
                ('user_agent', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
