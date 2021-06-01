# GitLab Group Member Report

Create a report of the members of a group, its subgroups and contained projects using the GitLab API and GitLab pages.

**This report is intended for auditing members.**

**To get the actual license count required, use Settings -> Billing on GitLab.com OR Admin Area -> License on self-managed**

## Features

- Queries a GitLab.com Group or all groups and projects on a self-managed instance
- queries all members of these groups and projects and their access level
- provides an aggregated report containing highest access level and the group or project where this level is assigned.
- provides individual reports for subgroups and projects (only direct members)
- If an instance admin token is used, additional user information like "last sign on" date and "status" is retrieved (if you want this on .com, upvote [this](https://gitlab.com/gitlab-org/gitlab/issues/33372)!). If not:
  - The script uses the [user events API](https://docs.gitlab.com/ee/api/events.html#get-user-contribution-events) to get an idea of last user activity even if no admin token is used
- Provides the date the user was created on the GitLab instance. For .com customers, this **may coincide** with the date the person was added to your group. This won't be available for users with private profiles.
- Produces HTML and JSON

## Configuration

- Export / fork repository.
- **Make it private, to prevent others from seeing your groups and their members**
- Add a GitLab API token to CI/CD variables named `GIT_TOKEN`. Make sure it is "masked".
This token will be used to query the API for group and project members
- Modify the gitlab-ci.yml to specify your groups, set instance mode or other changes according to the Parameters section of this readme
- Make sure Settings -> Permissions -> Pages is limited to project members
- Run the Pipeline to get your report
- Upvote this issue: https://gitlab.com/gitlab-org/gitlab/issues/27074

## Parameters

- `-u`, `--gitlaburl`: GITLABURL
- `-g`, `--groups`: Groups to report on. Can provide multiple groups, separated by whitespace (-g group1 group2)
- `-c`, `--csv`: Flag, Produce CSV files
- `-q`, `--query`: Flag, Query new, otherwise load JSONs and make html
- `-f`, `--filterfile`: Filepath to filter file. Format: one username per line. Filter file will filter users from results.
- `-i`, `--instance`: Query all groups the token owner has access to. If an admin token is used, that's all groups in the instance. Overrides 
-g selection.
- `-s`, `--squash`: Merge all groups into one file.
- `--nossl`: do not verify requests (**not recommended**, should you encounter ssl issues)

## Example usage

**Query a .com group, produce CSV files**

`python3 group_member_report.py -u https://gitlab.com -g $group_path -qc`

**Query all groups in the instance, produce separate CSV files for all groups**

`python3 group_member_report.py -u $instance_url -qic`

**Query all groups in the instance, produce one CSV file for all groups**

`python3 group_member_report.py -u $instance_url -qics`

## Who is using a license seat?

### GitLab.com

**Free, Bronze, Silver**

Every group member with Highest Access Level **higher than 0** is using a license seat. 

If a user is added to your GitLab.com group or any subgroup or project within, they will use a billable seat.

**Gold**

Every group member with Highest Access Level **higher than 10 (Guest)** is using a license seat.

### Self-managed

**Core, Starter, Premium**

Every user with **state = active** is using a license seat.

If a user is a member of the instance and they are not blocked or deactivated, they will use a billable seat.

Note that you need to use an admin token to get the additional "state" information out of this report.

**Ultimate**

Every user with Highest Access Level **higher than 10 (Guest) and state = active** is using a license seat.

## Disclaimer

This script is provided for educational purposes. It is not supported by GitLab. However, you can create an issue if you need help or better propose a Merge Request. This script creates a report of user names and, on self-managed, emails, which has the potential to leak personal data. Please use this script and its outputs with caution and in accordance to your local data privacy regulations.
