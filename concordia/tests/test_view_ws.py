# TODO: Add correct copyright header

import json
import time
from django.test import Client, TestCase
from rest_framework import status

from concordia.models import (PageInUse, User)


class ViewWSTest_Concordia(TestCase):
    """
    This class contains the unit tests for the view_ws in the concordia app.

    Make sure the postgresql db is available. Run docker-compose up db
    """

    def setUp(self):
        """
        setUp is called before the execution of each test below
        :return:
        """
        self.client = Client()

    def login_user(self):
        """
        Create a user and log the user in
        :return:
        """
        # create user and login
        self.user = User.objects.create(username="tester", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        self.client.login(username="tester", password="top_secret")

        # create a session cookie
        self.client.session['foo'] = 123  # HACK: needed for django Client

    def test_PageInUse_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        # Assert
        self.assert_post_successful(response)

    def test_PageInUse_delete_old_entries_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use
        the database has two items added the created_on timestamp of now - 10 minutes
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        from datetime import datetime, timedelta

        time_threshold = datetime.now() - timedelta(minutes=10)
        page1 = PageInUse(
            page_url="foo.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold)
        page1.save()

        page2 = PageInUse(
            page_url="bar.com/blah",
            user=self.user,
            created_on=time_threshold,
            updated_on=time_threshold)
        page2.save()

        pages_in_use = PageInUse.objects.all()
        for p in pages_in_use:
            print(p.page_url, p.created_on, p.updated_on)

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        # Assert
        self.assert_post_successful(response)



    def test_PageInUse_nologin_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging in
        :param self:
        :return:
        """

        # Arrange
        # create user
        self.user = User.objects.create(username="foo", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Verify the entry is not in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 0)

    def test_PageInUse_nologin_anonymous_post(self):
        """
        This unit test tests the post entry for the route ws/page_in_use without logging
        and the user is anonymous
        :param self:
        :return:
        """

        # Arrange
        # create user
        self.user = User.objects.create(username="anonymous", email="tester@foo.com")
        self.user.set_password("top_secret")
        self.user.save()

        # Act
        response = self.client.post(
            "/ws/page_in_use/",
            {
                "page_url": "transcribe/American-Jerusalem/asset/mamcol.0930/",
                "user": self.user.id,
            },
        )

        # Assert
        self.assert_post_successful(response)

    def assert_post_successful(self, response):
        """
        Check the results of a successful post and insert of a PageInUse database item
        :param response:
        :return:
        """
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify the entry is in the PagInUse table
        page_in_use = PageInUse.objects.all()
        self.assertEqual(len(page_in_use), 1)

    def test_PageInUse_get(self):
        """
        This unit test tests the get entry for the route ws/page_in_use/url
        :param self:
        :return:
        """

        # Arrange
        self.login_user()

        # Add two values to database
        PageInUse.objects.create(
            page_url="foo.com/blah",
            user=self.user)

        PageInUse.objects.create(
            page_url="bar.com/blah",
            user=self.user)

        # Act
        response = self.client.get("/ws/page_in_use/bar.com/blah/")

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertJSONEqual(
            str(response.content, encoding='utf8'),
            {"page_url": "bar.com/blah", "user": self.user.id }
        )

    def test_PageInUse_put(self):
        """
        This unit test tests the update of an existing PageInUse using PUT on route ws/page_in_use/url
        :return:
        """
        # Arrange
        self.login_user()

        # Add a value to database
        page = PageInUse(
            page_url="foo.com/blah",
            user=self.user)
        page.save()

        change_page_in_use = {"page_in_use": "foo.com/blah", "user": self.user.id}

        # sleep so update time can be tested against original time
        time.sleep(2)

        # Act
        response = self.client.put(
            "/ws/page_in_use_update/foo.com/blah",
            data=json.dumps(change_page_in_use),
            content_type='application/json'
        )

        all_pages = PageInUse.objects.all()
        for page in all_pages:
            print(page.page_url)
        # Assert
        self.assertEqual(response.status_code, status.HTTP_301_MOVED_PERMANENTLY)

        updated_page = PageInUse.objects.filter(page_url="foo.com/blah")
        self.assertTrue(len(updated_page), 1)
        self.assertEqual(page.id, updated_page[0].id)
        self.assertTrue(updated_page[0].updated_on > page.created_on)
