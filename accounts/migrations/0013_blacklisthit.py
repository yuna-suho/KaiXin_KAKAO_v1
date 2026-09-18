from django.db import migrations, models


def copy_bot_hits(apps, schema_editor):
    BotHit = apps.get_model('accounts', 'BotHit')
    BlacklistHit = apps.get_model('accounts', 'BlacklistHit')
    rows = [
        BlacklistHit(
            kind='bot',
            ip=hit.ip,
            reason=hit.reason,
            path=hit.path,
            user_agent=hit.user_agent,
            created_at=hit.created_at,
        )
        for hit in BotHit.objects.all().iterator()
    ]
    if rows:
        BlacklistHit.objects.bulk_create(rows, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_bothit'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlacklistHit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('manual', 'manual'), ('rate', 'rate'), ('login', 'login'), ('limit', 'limit'), ('mybox', 'mybox'), ('bot', 'bot')], db_index=True, max_length=16)),
                ('ip', models.CharField(db_index=True, max_length=45)),
                ('reason', models.CharField(blank=True, default='', max_length=32)),
                ('path', models.CharField(blank=True, default='', max_length=500)),
                ('user_agent', models.CharField(blank=True, default='', max_length=500)),
                ('detail', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='blacklisthit',
            index=models.Index(fields=['kind', '-created_at'], name='accounts_bl_kind_9e4d1a_idx'),
        ),
        migrations.AddIndex(
            model_name='blacklisthit',
            index=models.Index(fields=['kind', 'ip'], name='accounts_bl_kind_7c2b0e_idx'),
        ),
        migrations.RunPython(copy_bot_hits, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='BotHit',
        ),
    ]
