from django.db import migrations
import os

images_location = "/concordia_images"
item_prefix = "mss3782"

def populate_samples(apps, schema_editor):
    Asset = apps.get_model('transcribr', 'Asset')
    Subcollection = apps.get_model('transcribr', 'Subcollection')
    Collection = apps.get_model('transcribr', 'Collection')

    coll = Collection.objects.create(
        title='Branch Rickey Papers',
        slug='branch-rickey-papers',
        description='Branch Rickey Papers',
    )

    for item_path in os.listdir(images_location):
        if item_path.startswith(item_prefix):
            subcollection = Subcollection.objects.create(
                title=item_path,
                slug=item_path,
                collection=coll,
            )

            image_count = len(os.listdir(os.path.join(images_location, item_path)))

            for i in range(0, image_count):
                asset = Asset.objects.create(
                    title='{0} {1}'.format(item_path, i),
                    slug='{0}-{1}'.format(item_path, i),
                    description='',
                    media_url='transcribr/{0}/{1}.jpg'.format(item_path, i),
                    media_type='IMG',
                    collection=coll,
                    subcollection=subcollection,
                    sequence=i
                )


class Migration(migrations.Migration):

    dependencies = [
        ('transcribr', '0001_initial'),
        ('transcribr', '0002_faux_populate'),
        ('transcribr', '0003_clara_barton'),
    ]

    operations = [migrations.RunPython(populate_samples)]
