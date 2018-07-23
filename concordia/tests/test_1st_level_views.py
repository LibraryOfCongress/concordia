# TODO: Add correct copyright header

from django.test import Client, TestCase
from django.urls import reverse


class ViewTest_1st_level(TestCase):
    """
    This is a test case for testing all the first level views originated
    from home pages.

    """

    def setUp(self):
        """
        setUp is called before the execution of each test below
        :return:
        """
        self.client = Client()
    
    def test_contact_us_get(self):
        # Arrange

        # Act
        response = self.client.get(reverse("contact"))
        
        # Assert:
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'contact.html')