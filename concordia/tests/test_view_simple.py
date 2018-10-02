# TODO: Add correct copyright header

from django.test import TestCase


class ViewTest1(TestCase):
    """
    This is a simple django TestCase that
     can be used to prove the django test
      environment is properly configured.

    It doesn't test any component of the concordia project.
    """

    def setUp(self):
        """
        setUp is called before the execution of each test below
        :return:
        """
        pass

    def test_addition(self):

        x = 1
        y = 2

        sum = x + y

        self.assertEqual(sum, 3)

    def test_addition2(self):

        x = 4
        y = 2

        sum = x + y

        self.assertEqual(sum, 6)

    def test_addition3(self):

        x = 5
        y = 2

        sum = x + y

        self.assertEqual(sum, 7)
