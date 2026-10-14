from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('target', '0019_alter_target_rules'),
    ]

    operations = [
        migrations.AlterField(
            model_name='target',
            name='rules',
            field=models.TextField(blank=True, default="\nMake words of at least four letters using the grid letters at most once. The centre letter must be in every word. There's one nine-letter word.\n\nExcept possibly for the nine-letter target:\n- There are no plurals ending in s. (But geese would be allowed.)\n- There are no third-person singular verbs ending in s (e.g. cooks in ‘he cooks bobotie’).\n- There are no proper nouns.\n\nThe nine-letter target can break any of the above rules however. It often has a South African flavour. It is often two words and could even be three or more.\n\nWords are drawn from our dictionary which has about 70,000 words. You can either type the letters or click on them. To delete a letter use the backspace key or click it again."),
        ),
    ]
