# Contributing to Apache-BigData-SIEM

First off, thank you for considering contributing to Apache-BigData-SIEM! It's people like you that make Apache-BigData-SIEM such a great tool for the security community.

## Where do I go from here?

If you've noticed a bug or have a feature request, make sure to check our [Issues](../../issues) to see if someone else in the community has already created a ticket. If not, go ahead and make one!

## Fork & create a branch

If this is something you think you can fix, then fork Apache-BigData-SIEM and create a branch with a descriptive name.

A good branch name would be (where issue #325 is the ticket you're working on):

```sh
git checkout -b 325-add-new-parser
```

## Get the test suite running

Make sure you have Docker and Docker-Compose installed. Verify the environment is running:

```sh
make up
```

## Implement your fix or feature

At this point, you're ready to make your changes. Feel free to ask for help on the issue tracker if you need some guidance!

## Make a Pull Request

At this point, you should switch back to your master branch and make sure it's up to date with Apache-BigData-SIEM's master branch:

```sh
git remote add upstream git@github.com:yusufarbc/Apache-BigData-SIEM.git
git checkout master
git pull upstream master
```

Then update your feature branch from your local copy of master, and push it!

```sh
git checkout 325-add-new-parser
git rebase master
git push --set-upstream origin 325-add-new-parser
```

Finally, go to GitHub and make a Pull Request! Please use the provided PR template to ensure all necessary information is provided.

## Guidelines

- We use Python 3.x and PySpark.
- Please write readable, well-documented code.
- Provide unit tests or verification steps (in `docs/verification-guide.md`) for any new features or parsers.
- Use meaningful commit messages.

Thank you for contributing!
