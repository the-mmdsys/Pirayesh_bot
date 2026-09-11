from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Concat, Substr, Trim


def backfill(apps, schema_editor):
    BotUser = apps.get_model('appointments', 'BotUser')
    BotUser.objects.using(schema_editor.connection.alias).filter(full_name='').update(
        full_name=Substr(Trim(Concat('first_name', Value(' '), 'last_name')), 1, 200),
    )


class Migration(migrations.Migration):
    dependencies = [('appointments', '0006_barber_biography_barber_experience_years_and_more')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
