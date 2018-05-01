from django.test import TestCase
from django.test import Client


class ViewTest1(TestCase):
    def setUp(self):
        print("In setup")
        pass

    def test_addition(self):
        # Arrange
        x = 1
        y = 2

        # Act
        sum = x + y

        print("Sum", sum)

        # Assert
        self.assertEqual(sum, 3)

    def test_addition2(self):
        # Arrange
        x = 4
        y = 2

        # Act
        sum = x + y

        print("Sum", sum)

        # Assert
        self.assertEqual(sum, 6)


    def test_addition3(self):
        # Arrange
        x = 5
        y = 2

        # Act
        sum = x + y

        print("Sum", sum)

        # Assert
        self.assertEqual(sum, 7)



