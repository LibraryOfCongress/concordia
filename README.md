[![Build Status](https://travis-ci.org/LibraryOfCongress/concordia.svg?branch=master)](https://travis-ci.org/LibraryOfCongress/concordia)
[![Coverage Status](https://coveralls.io/repos/github/LibraryOfCongress/concordia/badge.svg?branch=master)](https://coveralls.io/github/LibraryOfCongress/concordia?branch=master)

# Welcome to Concordia

Concordia is a platform developed by the Library of Congress (LOC) for crowdsourcing transcription and tagging of text in digitized images with the dual goals of collection enhancement and public engagement. Concordia is a user-centered project centering the principles of trust and approachability. [Read our full design principles here](https://github.com/LibraryOfCongress/concordia/blob/master/docs/design-principles.md).

The Library of Congress publishes transcriptions created by volunteers through Concordia on [loc.gov](https://www.loc.gov/) to improve search, readability, and access to handwritten and typed documents. Individual transcriptions are published alongside the transcribed images in digital collections and transcriptions are also published in bulk as [datasets](https://www.loc.gov/search/?fa=contributor:by+the+people+%28program%29).

Concordia code and the By the People transcriptions are released into the public domain. Anyone is free to use or reuse the data. [More info on our licensing page](https://github.com/LibraryOfCongress/concordia/blob/main/LICENSE.md).

LOC launched the first iteration of Concordia as [By the People at crowd.loc.gov](https://crowd.loc.gov/) in October 2018. Learn more about the Concordia development process in [this Code4Lib article](https://journal.code4lib.org/articles/14901).

As of May 2022 the Library of Congress Concordia development team has moved issues out of Github to an internal system due to reporting needs.  Open github issue tickets may not be active or up-to-date. We continue to publish our code here as it is released. Learn more about [How We Work](https://github.com/LibraryOfCongress/concordia/blob/main/docs/how-we-work.md).

_Concordia and By the People are supported by the National Digital Library Trust Fund._

## What Concordia does

The application invites volunteers to transcribe and tag digitized images of manuscript and typed materials from the Library’s collections. All transcriptions are made by volunteers and reviewed by volunteers. It takes at least one volunteer to transcribe a page and at least one other volunteer to review and mark it complete. Some complex documents may pass through both transcription and review many times before they are accepted as complete. 

Concordia is a containerized Python-Django-Postgres-etc web application. The Library hosts its instance in the cloud.

Concordia leverages the publicly-available [loc.gov API](https://libraryofcongress.github.io/data-exploration/) to call collection metadata and images in JPEG format and save copies for use in Concordia. Completed transcriptions can be exported out of the application as a single CSV or individual TXT files in a BagIt bag.

## Want to use or reuse our code?
For more on our tech stack and to learn how to set up the Concordia on your computer, check out the [For Developers page](docs/for-developers.md).

## Want to help?

We're excited that you want to be part of Concordia! Here are two ways to contribute:

__1. Report bugs by submitting an issue.__ If you are reporting a bug, please include:
- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

__2. Create an issue to give feedback or suggest a new feature.__ The best way to give feedback is to file an issue at https://github.com/LibraryOfCongress/concordia/issues. If you are proposing a feature:
- Explain in detail how it would work.
- Explain how it would serve Concordia via a user story
- Keep the scope as narrow as possible, to make it easier to implement.

If you use or build on our code, we'd love to hear from you! Contact us here or at [crowd@loc.gov](mailto:crowd@loc.gov).
