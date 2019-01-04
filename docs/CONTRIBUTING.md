# Contributing

Contributions are welcome and are greatly appreciated! Every little bit helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs by [submitting an issue](https://github.com/LibraryOfCongress/concordia/issues).

If you are reporting a bug, please include:

-   Your operating system name and version.
-   Any details about your local setup that might be helpful in troubleshooting.
-   Detailed steps to reproduce the bug.

### Submit a pull request to fix bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" is open to whoever wants to implement it.

### Submit a pull request to implement features

Look through the GitHub issues for features. Anything tagged with "feature" is open to whoever wants to implement it.

### Write Documentation

Concordia could always use more documentation. If you have worked with the tool and found any of our documentation to be inaccurate or vague, please submit an issue or a pull request.

### How to submit Feedback

The best way to send feedback is to file an issue at https://github.com/LibraryOfCongress/concordia/issues.

If you are proposing a feature:

-   Explain in detail how it would work.
-   Keep the scope as narrow as possible, to make it easier to implement.
-   Remember that this is a volunteer-driven project, and that contributions
    are welcome :)

### Get Started!

Ready to contribute? Check out our [Developers Guide](https://github.com/LibraryOfCongress/docs/for-developers.md) on how to set up your machine for local development. You'll need Docker and Python 3 with pip and pipenv.

1. Fork the `concordia` repo on GitHub.
2. Clone your fork locally:

    #### Git Bash

    ```
    $ git clone git@github.com:YOUR_USERNAME/concordia.git
    ```

    #### GitHub Desktop

    File > Clone Repository > YOUR_USERNAME/concordia

3. Install your local copy to your virtual environment. Follow the instructions in the [Developers Guide](https://github.com/LibraryOfCongress/docs/for-developers.md).

4. Create a branch for local development:

    #### Git Bash

    ```
    `$ git checkout -b name-of-your-bugfix-or-feature`
    ```

    #### GitHub Desktop

    Branch > New Branch > NAME_OF_BRANCH > Create new branch

    Now you can make your changes locally.

5. Commit your changes and push your branch to GitHub:

    #### Git Bash

    ```
    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature
    ```

    #### GitHub Desktop

    I. Enter Commit Message

    II. Enter in optional extended description

    III. Select commit to YOUR_BRANCH

    IV. Click Push to Origin

6. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.rst.
3. The pull request should work for Python `3.6`
