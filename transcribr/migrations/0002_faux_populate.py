from django.db import migrations
from django.contrib.auth.hashers import make_password


def populate_samples(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Asset = apps.get_model('transcribr', 'Asset')
    Subcollection = apps.get_model('transcribr', 'Subcollection')
    Tag = apps.get_model('transcribr', 'Tag')
    UserAssetTagCollection = apps.get_model('transcribr', 'UserAssetTagCollection')
    Transcription = apps.get_model('transcribr', 'Transcription')
    Collection = apps.get_model('transcribr', 'Collection')

    coll = Collection.objects.create(
        title='Clara Barton',
        slug='clara-barton',
        description='Clara Barton Collection',
    )

    subcollection = Subcollection.objects.create(
        title='Journal #1',
        slug='journal-1',
        collection=coll,
    )
    
    for i in range(1,5):
        asset_a = Asset.objects.create(
            title='CB Asset {}'.format(i),
            slug='cb-asset-{}'.format(i),
            description='CB Asset {} description'.format(i),
            media_url='transcribr/mss119730001/{0}.jpg'.format(i),
            media_type='IMG',
            collection=coll,
            subcollection=subcollection,
            sequence=i
        )

    for i in range(5,7):
        asset_b = Asset.objects.create(
            title='CB Asset {}'.format(i),
            slug='cb-asset-{}'.format(i),
            description='CB Asset {} description'.format(i),
            media_url='transcribr/mss119730001/{0}.jpg'.format(i),
            media_type='IMG',
            collection=coll,
            sequence=1
        )
    
    tags = []
    for char in 'ABCDEFGHIJK':
        txt = 'Tag {}'.format(char)
        tag = Tag.objects.create(name=txt, value=txt)
        tags.append(tag)

    user = User(username='user', email='user@example.com')
    user.password = make_password('password')
    user.save()

    uatc = UserAssetTagCollection.objects.create(asset=asset_a, user_id=user.id)
    uatc.tags.add(*tags[:3])
    Transcription.objects.create(
        asset=asset_a,
        user_id=user.id,
        text='Lorem ipsum dolor sit amet, consectetur adipisicing elit. Recusandae tempore ratione'
             ' explicabo numquam voluptates labore perspiciatis minima, in dolor maiores vitae dolorum, '
             'nobis rerum voluptatem cupiditate libero officiis tenetur soluta!',
        status='25',        
    )

    uatc = UserAssetTagCollection.objects.create(asset=asset_b, user_id=user.id)
    uatc.tags.add(tags[3])
    Transcription.objects.create(
        asset=asset_b,
        user_id=user.id,
        text='Here are some words',
        status='75',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('transcribr', '0001_initial'),
    ]

    operations = [migrations.RunPython(populate_samples)]
