from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_unknown_block'),
    ]

    operations = [
        migrations.DeleteModel(
            name='BlacklistHit',
        ),
    ]
