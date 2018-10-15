# How We Work

## Principles

Our basic principles are those familiar to anybody who has contributed to a prominent open source project, or deployed code in a modern software environment:

-   We produce open source software, created and maintained in repositories where it may be inspected by the public who places their trust in it and copied for use by other agencies or institutions.
-   We adhere to the basic practices of agile software development, using the Scrum development framework.
-   We practice human-centered design. Everything that we produce is highly accessible, per [WCAG 2.1](https://www.w3.org/TR/WCAG21/).
-   Finally, we believe in having the relevant decision-makers at the table during all meetings, to maximize efficiency and maintain momentum.

## Product Team

There is a cross functional product team for Concordia comprised of Library Services, policy, security, and technical specialists who are working together. This product team will be comprised of the following roles

-   Product owner
-   Product manager
-   Technical lead
-   User Experience designer
-   Developers (Front-end, Back-end, Full-stack)

This team will participate in all stand ups, backlog grooming and retrospectives in service of prioritizing, defining and delivering value to the department and the public it serves.

## Sprint Organization and Meetings

Each sprint is two weeks long. We have a sprint kick off the first day of the new sprint. There are three basic meeting rhythms:

-   Daily standups at 10:30 - 10:45 am
    -   Structure: Each team member talks says what they completed yesterday, what they will work on today, and any blockers
-   Weekly backlog grooming on Thursday at 3:00 – 4:30 pm
    -   Structure: tickets in the backlog are sorted by priority, the team adds acceptance criteria, story points and assigns the tasks to a team member
-   Sprint demo and retrospectives are held every two weeks
    -   At the end of each sprint, the PM demos work completed in the sprint for the larger library stakeholders followed by a retrospective of just the product team. These are held back-to-back, on the same day

All meetings are held in person, on Slack or WebEx, a video teleconference application.

## Definition of Done

So that we can work more efficiently and be confident in the quality of the work we are delivering, we have a clear definition of what it means for a user story to be done, or production-ready.

-   **For delivering a user story to the product team:**
    -   Story needs to be written in a way that is clear from both a development and a testing standpoint. Stories will need to be reviewed by the product team during creation.
    -   Acceptance criteria should include the relevant tests needed (unit, security, performance, acceptance, etc)
    -   Acceptance criteria should include the objective of the story, for use in approval by PO or tech team or both - The delivered functionality should match the acceptance criteria of the user story
-   **for product team to accept the user story and ship it**
    -   The functionality meets the acceptance criteria
    -   The product team has verified the functionality in staging
    -   All tests must pass in the the stage environment (unit, integration, feature)
    -   The delivered functionality should be 508 compliant
    -   Security requirements must be met - All documentation must be up to date (diagrams, training documentation, API documentation, help text, etc)
    -   The delivered functionality should be compatible with the latest versions of IE, Firefox, Chrome and Safari

## Processes

#### Testing Strategy

We practice testing at three levels: unit tests, integration tests, and feature tests. For details about how we create and maintain unit, integration and feature tests.

-   Unit - Unit tests must be created for all new code, during the sprint in which the code is written, with coverage of at least 90%.
-   Integration - Code must include tests that verify that interfaces are functioning as designed.
-   Feature - New features must have functional definitions of the thing that they are to perform, and a description of human-performable actions to verify that they perform that thing.

## Branch strategy and Pull Request Process

# Git branching strategy

We will have two long-lived git branches, `master` and `staging`.

`master` will continuously deploy to our production environment.

`staging` will continuously deploy to our staging environment.
Our staging environment will be on AWS and only accessible through the library's network.

## Starting new work

When someone begins new work, they cut a new branch from `staging` and name it after their work, perhaps `feature1`. New changes are pushed to the feature branch origin. Continuous Integration (CI) will be triggered on PR to `staging`.

## Merging to `staging`

When new work is complete, we set up a Pull Request (PR) from `feature1` to `staging`. Discussion about, and approval of changes by either the technical lead, Product Owner or both happens in the PR interface in GitHub

Once this new work is approved we close the PR, which merges the code.
From here, our CI pipeline will build the new changes on the `staging` branch. Next, our CD pipeline will deploy the new work to our staging environment.

## Merging to `master`

Once a new body of work is merged to `staging` (likely via multiple PRs) and any manual QA work has finished in the staging environment, we set up a PR from `staging` to `master`.

This constitutes a new production release. Any last-minute discussion, as well as approval happens in the PR interface. Once approved by the technical lead, product owner or both and merged, CI runs for `master` branch to the production environments.

## Race conditions on merges to staging

Imagine two PRs called A and B are open against the `staging` branch. The two PRs both change code in the same file. Now, we merge PR A to staging. After this merge PR B will report that it is "unmergeable" in GitHub. This is because `staging` contains the changes from PR A, but PR B does not contain those changes -- git doesn't know what to do.

In this case we have a couple options.

1. Rebase: `git rebase B_branch staging`. Rebasing the branch replays all of the commits from B on top of the _new_ `staging` branch (which now contains changes from A). **Rebasing is the preferred method for handling these issues.** Push the `B_branch` and you'll be able to use GitHub to close the PR.
2. Manual conflict resolution. Instead of using the GitHub UI to merge the PR, execute the merge locally. `git checkout staging && git merge B_branch`. Git will report merge conflicts, which you can resolve locally, manually, using your editor. When you're done push the `staging` branch and close the PR in GitHub

## Patching production/master

Imagine that many PRs have been merged to `staging`, and you find a problem in production that needs a quick fix. At this point `staging` has moved far past `master`. In this case we code the fix to production in a new branch cut from `master`, maybe called `prod_fix`. We set up a PR against `master` for reiew and discussion.

Any QA or manual testing will take place in a one-off environment deployed from the `prod_fix` branch; with the Azure PaaS we could manually deploy to an empty Deployment Slot. Once the PR on `master` is merged CI/CD takes care of deployment to the production environment.

Now we have to bring those new changes in master back into staging. We use rebase again: `git rebase staging master`.

## Code quality and review process

Code reviews are about keeping code clean and limiting technical debt. We will look for things that increase technical debt or create an environment where technical debt can be introduced easily later. Each pull request will be reviewed by the technical lead or assigend reviewer. As a reviewer, they will look closely to untested code, if there are tests that they are testing what they're supposed to, that they are following the Library's code standards.

### Ensuring your work follows the Library's coding standards

The project extends the standard Django settings model for project configuration and the Django test framework for unit tests.

#### Configuring your virtual env

The easiest way to install the site is using [Pipenv](https://pipenv.readthedocs.io/) to manage the virtual environment and install dependencies.

#### Configure your local checkout with code-quality hooks

1. Install [pre-commit](https://pre-commit.com/)
1. Run `pre-commit install`

Now every time you make a commit in Git the various tools listed in the next
section will automatically run and report any problems.

#### Configure your editor with helpful tools:

[setup.cfg](setup.cfg) contains configuration for pycodestyle, [isort](https://pypi.org/project/isort/) and flake8.

Configure your editor to run black and isort on each file at save time.

1. Install [black](https://pypi.org/project/black/) and integrate it with your editor of choice.
2. Run [flake8](http://flake8.pycqa.org/en/latest/) to ensure you don't increase the warning count or introduce errors with your commits.
3. This project uses [EditorConfig](https://editorconfig.org) for code consistency.

If you can't modify your editor, here is how to run the code quality
tools manually:

```
    $ black .
    $ isort --recursive
```

Black should be run prior to isort. It's recommended to commit your code
before running black, after running black, and after running isort so
the changes from each step are visible.

## Tools we use

-   GitHub - We use our GitHub organization for storing both software and collaboratively-maintained text.
-   Slack - We use the Slack for communication that falls outside of the structure of Jira or GitHub, but that doesn’t rise to the level of email, or for communication that it’s helpful for everybody else to be able to observe.
-   WebEx - We use WebEx for video conferencing in all our meetings
