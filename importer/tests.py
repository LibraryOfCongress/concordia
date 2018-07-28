import json

from django.test import TestCase, Client
from django.urls import reverse

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from importer.tasks import *


class CreateCollectionViewTest(TestCase):
    """ Test module for CreateCollectionView API """

    def setUp(self):
        self.valid_item_input = {
            'name': 'Rosa-Parks-Papers',
            'url': 'https://www.loc.gov/item/mss859430021',
            'create_type': 'item'
        }

        self.valid_collection_input = {
            'name': 'digital-collection',
            'url': 'https://www.loc.gov/collections/?fa=partof:law+library+of+congress',
            'create_type': 'item'
        }

    def test_create_item_collection(self):
        client = Client()
        response = client.post(
            reverse('create_collection'),
            data=json.dumps(self.valid_item_input),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_collection(self):
        client = Client()
        response = client.post(
            reverse('create_collection'),
            data=json.dumps(self.valid_collection_input),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_invalid_collection(self):
        client = Client()
        response = client.post(
            reverse('create_collection'),
            data=json.dumps('https://www.loc.gov/collectionsdd/?fa=partof:law+library+of+congress'),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ImporterTasksTest(TestCase):
    """Test module for all importer tasks functions"""

    def setUp(self):
        self.valid_test_data = {
            'name': 'Rosa-Parks-Papers',
            'url': 'https://www.loc.gov/item/mss859430021?fo=json',
            'create_type': 'item',
        }

        self.valid_collection_test_data = {
            'name': 'Rosa-Parks-Papers',
            'url': 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971',
            'create_type': 'item',
            'no_of_pages': 1
        }

        self.invalid_collection_test_data = {
            'name': 'Rosa-Parks-Papers',
            'url': 'https://www.loc.gov/item/mss859430021?fo=json',
            'create_type': 'item',
            'no_of_pages': 0
        }

    def test_get_request_data(self):
        response = get_request_data(self.valid_test_data['url'])
        self.assertEqual(dict, type(response))
        self.assertIn('https://www.loc.gov/resource/mss85943' , response['resources'][0]['url'])

    def test_get_collection_pages(self):
        response = get_collection_pages(self.valid_collection_test_data['url'])
        self.assertEqual(int, type(response))
        self.assertEqual(response, self.valid_collection_test_data['no_of_pages'])

    def test_get_collection_pages_for_invalid_collection(self):
        response = get_collection_pages(self.invalid_collection_test_data['url'])
        self.assertEqual(int, type(response))
        self.assertEqual(response, self.invalid_collection_test_data['no_of_pages'])

    def test_get_collection_params_without_fa(self):
        curl, cparams = get_collection_params(self.invalid_collection_test_data['url'])
        self.assertEqual(curl, self.invalid_collection_test_data['url'])
        self.assertEqual(cparams, {})

    def test_get_collection_params_with_fa(self):
        test_url = 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'
        curl, cparams = get_collection_params(test_url)
        self.assertEqual(curl, test_url.split("?fa")[0])
        self.assertIn('partof', cparams.get('fa'))

    def test_get_collection_item_ids(self):
        test_url = 'https://www.loc.gov/collections/branch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'
        name = 'branch-rickey-papers'
        response = get_collection_item_ids(name, test_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.status_text, 'OK')
        self.assertEqual(response.data, {"message": "Unable to create item entries for collection : branch-rickey-papers"})

    def test_get_collection_item_ids_invalid_response(self):
        test_url = 'https://www.loc.gov/collections/ibbbranch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971'
        name = 'branch-rickey-papers'
        response = get_collection_item_ids(name, test_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.status_text, 'OK')
        self.assertEqual(response.data, {"message": 'No page results found for collection : "https://www.loc.gov/collections/ibbbranch-rickey-papers/?fa=partof:branch+rickey+papers:+baseball+file,+1906-1971" from loc API'})
