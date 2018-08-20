# documents.py

from django_elasticsearch_dsl import DocType, Index
from django.contrib.auth.models import User

# Name of the Elasticsearch index
user = Index('users')
# See Elasticsearch Indices API reference for available settings
user.settings(
    number_of_shards=1,
    number_of_replicas=0
)


@user.doc_type
class UserDocument(DocType):
    class Meta:
        model = User  # The model associated with this DocType

        # The fields of the model you want to be indexed in Elasticsearch
        fields = [
            'last_login',
            'date_joined'
        ]

        # Ignore auto updating of Elasticsearch when a model is saved
        # or deleted:
        # ignore_signals = True
        # Don't perform an index refresh after every update
        # (overrides global setting):
        # auto_refresh = False
        # Paginate the django queryset used to populate the index with
        # the specified size
        # (by default there is no pagination)
        # queryset_pagination = 5000
