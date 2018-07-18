# How We Work
## Principles

##### Our basic principles are those familiar to anybody who has contributed to a prominent open source project, or deployed code in a modern software environment:

- We produce open source software, created and maintained in repositories where it may be inspected by the public who places their trust in it and copied for use by other agencies or institutions.
- We adhere to the basic practices of agile software development, using the Scrum development framework.
- We practice human-centered design. Everything that we produce is highly accessible, per [WCAG 2.1]( https://www.w3.org/TR/WCAG21/). 
- Finally, we believe in having the relevant decision-makers at the table during all meetings, to maximize efficiency and maintain momentum.

## Product Team

There is a cross functional product team for Concordia comprised of Library Services, policy, security, and technical specialists who are working together. This product team will be comprised of the following roles
- Product owner – Library 
- Product manager(s) – Library
- Scrum Master (or equivalent) – Library 
- User Experience designer – Vendor 
- Developers (Front-end, Back-end, Full-stack) – Vendor 
- Technical lead – Vendor 

This team will participate in all stand ups, backlog grooming and retrospectives in service of prioritizing, defining and delivering value to the department and the public it serves.

## Sprint Organization and Meetings

Each sprint is two weeks long. We have a sprint kick off the first day of the new sprint. There are three basic meeting rhythms: 
- Daily standups at 10:00 – 10:30 am
    - Structure: Each team member talks says what they completed yesterday, what they will work on today, and any blockers
- Weekly backlog grooming on Thursday at 3:00 – 4:30 pm
    - Structure: tickets in the backlog are sorted by priority, the team adds acceptance criteria, story points and assigns the tasks to a team member
- Sprint demo and retrospectives are held every two weeks
    - At the end of each sprint, Artemis demos work completed in the sprint for the larger library stakeholders followed by a retrospective of just the product team. These are held back-to-back, on the same day

All meetings are held via WebEx, a video teleconference application. 

## Definition of Done

So that we can work more efficiently and be confident in the quality of the work we are delivering, we have a clear definition of what it means for a user story to be done, or production-ready.
- for delivering a user story to the product team
    - Story needs to be written in a way that is clear from both a development and a testing standpoint. Stories will need to be reviewed by the product team during creation. 
    - Acceptance criteria should include the relevant tests needed (unit, security, performance, acceptance, etc)
	- Acceptance criteria should include the objective of the story, for use in approval by PO or tech team or both
	- The delivered functionality should match the acceptance criteria of the user story
	- All tests must pass in the Artemis stage environment (unit, integration, feature)
	- The delivered functionality should be 508 compliant
	- Security requirements must be met
	- All documentation must be up to date (diagrams, training documentation, API documentation, help text, etc)
	- The delivered functionality should be compatible with the latest versions of IE, Firefox, Chrome and Safari
- for product team to accept the user story and ship it
	- The product team has verified the functionality in staging

## Accepting Vendor Work

Acceptance of work happens through the sprint as work is completed. The procedure is as follows:
- Development team completes work - See "for for delivering a user story to the product team" in Definition of Done above
- Development team creates pull request to staging - See Pull Request Process
- The product team has verified the functionality against acceptance criteria in a deployed instance for a feature level pull request
- Code review takes place - See Code Review Process
- Pull request merged to staging DHSS code reviewer
- User testing happens - See "for product team to accept the user story and ship it" in Definition of Done above, and Testing Strategy
- Product team creates pull request to master
- Library's technical lead merges pull request to master

## Processes
#### Testing Strategy

We practice testing at three levels: unit tests, integration tests, and feature tests. For details about how we create and maintain unit, integration and feature tests.
- Unit - Unit tests must be created for all new code, during the sprint in which the code is written, with coverage of at least 90%.
- Integration - Code must include tests that verify that interfaces are functioning as designed.
- Feature - New features must have functional definitions of the thing that they are to perform, and a description of human-performable actions to verify that they perform that thing.

## Branch strategy and Pull Request Process

We have two long lived git branches Artemis `master` and LOC `master`

Artemis `master` will continuously deploy to our staging site `chc-stage.artemisconsultinginc.com` and is the main repository for development

LOC `master` will be updated at the end of each sprint. This is the main repository for production (Once ATO is approved)

#### Starting new work

When someone begins new work, they cut a branch from Artemis `master` and name it after their work and the ticket number corresponding to Jira. Here is the format: `name-ticketnumber-task` example `tim-chc-167-tests-comments`. New changes are pushed to the feature branch of its origin often. 

#### Merging to Artemis `master`

When new work is complete, we set up a Pull Request (PR) from `name-ticketnumber-task` to Artemis `master`. Discussion and approval changes happens in the PR in the GitHub interface. In each Pull Request, in the description box should include: 
- details of the new work 
- Ticket numbers the PR addresses 
- Provide directions on how to test and review the PR 
- Assign a reviewer

Once this new work is approved we closed the PR, which merges the code. From here, a Jenkis job will run the build and deploy the new work at the end of the day. 

#### Merging to LOC `master`

At the end of each sprint, a PR will be made from the Artemis repo to LOC's `master`. All PR to LOC `master` should include:

- Sprint number
- Description of all new features 

All code at this point has been reviewed and approved but the product team. 


**Here is a table mapping out the full process**

| Stage                    | To Do                                             | In Progress                                             | Artemis Review                                                        | LOC Review                                                    | Complete                                                                   |
|--------------------------|---------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------------------------|---------------------------------------------------------------|----------------------------------------------------------------------------|
|                          |                                                   |                                                         |                                                                       |                                                               |                                                                            |
| **Actions**                  | Queue of tickets in to be completed in the sprint | Developer creates feature branch from [Artemis/Concorida](https://github.com/ArtemisConsulting/concordia) | Upon Completion developer submits pull request to Artemis/Concordia   | After passing Artemis Review ticket is moved to Review (Jira) | After passing Project Review ticket is moved to Done (Jira)                |
|                          |                                                   |                                                         | Moves ticket to Artemis Review column                                 | Moves ticket to LOC Review Column                             |                                                                            |
|                          |                                                   |                                                         | Pull Request is reviewed to meet coding standards                     | Feature Branch is merged with Artemis/Concordia/Master        | Artemis/Concordia/Master is merged with LibraryOfCongress/Concordia/Master |
|                          |                                                   |                                                         | Pull Request is reviewed to for functionality and acceptance criteria | Pull Request is submitted to LibraryOfCongress/Concordia      |                                                                            |
|                          |                                                   |                                                         |                                                                       |                                                               |                                                                            |
| **Artemis Hosting Location** |                                                   | AWS or Local Dev Environment [Artemis/Concordia/branch] | AWS or Local Dev Environment [Artemis/Concordia/branch]               | chc-stage [Artemis/Concordia/Master]                          | chc-test [LibraryOfCongress/Concordia/Master]                              |


## Code Review Process

TBD

## Tools

- GitHub - We use our GitHub organization for storing both software and collaboratively-maintained text.
- Slack - We use the Slack for communication that falls outside of the structure of Jira or GitHub, but that doesn’t rise to the level of email, or for communication that it’s helpful for everybody else to be able to observe.
- WebEx - We use WebEx for video conferencing in all our meetings

