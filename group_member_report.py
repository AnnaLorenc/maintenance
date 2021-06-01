#!/usr/bin/env python3

import json
import csv
import os
import sys
import argparse
import requests
import html
import time
from datetime import datetime
from mako.template import Template

def get_sub_groups(api_url, group_id, page, grouplist):
    groups = requests.get("%s/groups/%s/subgroups?page=%s&per_page=%s" % (api_url, group_id, page, per_page), headers=headers, verify=do_verify)
    if groups:
        if len(groups.json()) > 0:
            for group in groups.json():
                group_object = requests.get("%s/groups/%s" % (api_url, group["id"]), headers=headers, verify=do_verify)
                if group_object:
                    grouplist.append(group_object.json())
                    get_sub_groups(api_url, group["id"], 1, grouplist)
                else:
                    print("Failed to retrieve group details: %s" % group_id, file=sys.stderr)
            if len(groups.json()) == per_page:
                page += 1
                get_sub_groups(api_url, group_id, page, grouplist)
    else:
        print("Failed to retrieve groups in %s." % group_id, file=sys.stderr)

def get_projects(api_url, groups, page, do_archived):
    projectlist = []
    for group in groups:
        projects = None
        projects = requests.get("%s/groups/%s/projects?page=%s&per_page=%s&with_shared=false&archived=%s" % (api_url, group["id"], page, per_page, do_archived), headers=headers, verify=do_verify)
        if projects:
            if len(projects.json()) > 0:
                projectlist.extend(projects.json())
                if len(projects.json()) == per_page:
                    page += 1
                    print("Getting next page for projects " + str(page))
                    projectlist.extend(get_projects(api_url, groups, page, do_archived))
        else:
            print("Failed to retrieve projects in %s: %s" % (grouptype, group["name"]), file=sys.stderr)
    return projectlist

def get_top_groups(api_url, page, grouplist = None):
    if grouplist is None:
        grouplist = []
    groups = requests.get("%s/groups?page=%s&per_page=%s" % (api_url, page, per_page), headers=headers, verify=do_verify)
    if groups:
        for group in groups.json():
            #this is a root group
            if "/" not in group["full_path"]:
                grouplist.append(group["full_path"])

        if len(groups.json()) == per_page:
            page += 1
            print("Getting next page for top groups " + str(page))
            get_top_groups(api_url, page, grouplist)
    else:
        print("Failed to retrieve top groups", file=sys.stderr)
    return grouplist

# decide between group and project based on grouptype
def get_group_members(api_url, group, page, grouptype, highest_level = None, inherited = None ):
    print("Getting members of " + group["name"])
    try:
        if inherited:
            users = requests.get("%s/%s/%s/members/all?page=%s&per_page=%s" % (api_url, grouptype, group["id"], page, per_page), headers=headers, verify=do_verify)
        else:
            users = requests.get("%s/%s/%s/members?page=%s&per_page=%s" % (api_url, grouptype, group["id"], page, per_page), headers=headers, verify=do_verify)
        if users:
            for user in users.json():
                if highest_level is not None:
                    user["shared_from_group"] = [group["name"], group["id"], group["full_path"], "shared group"]
                    if user["access_level"] > highest_level:
                        user["access_level"] = highest_level
                else:
                    user["shared_from_group"] = None
                if "members" in group:
                    group["members"].append(user)
                else:
                    group["members"] = [user]
            if len(users.json()) == per_page:
                page += 1
                print("Getting next page for users " + str(page))
                get_group_members(api_url, group, page, grouptype, inherited)
        else:
            print("Failed to retrieve members in %s: %s" % (grouptype, group["name"] ), file=sys.stderr)
            return False
    except:
        print("Failed to retrieve members in %s: %s" % (grouptype, group["name"] ), file=sys.stderr)
        return False

    path = group["full_path"] if grouptype == "groups" else group["path_with_namespace"]
    # the project has shared groups, so we want to know who are the members and add them to this project
    if "shared_with_groups" in group:
        for shared_group in group["shared_with_groups"]:
            print("%s is shared with group %s. Retrieving its members." % (path, shared_group["group_full_path"]), file=sys.stderr)
            shared_group["name"] = shared_group["group_name"]
            shared_group["id"] = shared_group["group_id"]
            shared_group["full_path"] = shared_group["group_full_path"]
            success = get_group_members(api_url, shared_group, 1, "groups" , shared_group["group_access_level"], True)
            if not success:
                if "failed_to_retrieve" in group:
                    group["failed_to_retrieve"].append(shared_group["group_full_path"])
                else:
                    group["failed_to_retrieve"] = [shared_group["group_full_path"]]
            else:
                for member in shared_group["members"]:
                    if "members" in group:
                        group["members"].append(member)
                    else:
                        group["members"] = [member]
    if "members" not in group:
        group["members"] = []
    return True

def add_user(userlist, path, userdict, group_url):
    for user in userlist:
        if user["id"] in userdict.keys():
            if user["access_level"] > userdict[user["id"]]["highest_access_level"]:
                userdict[user["id"]]["highest_access_level"] = user["access_level"]
            userdict[user["id"]]["groups"].append([ path, user["access_level"], group_url, user["shared_from_group"] ])
        else:
            user["name"] = html.escape(user["name"])
            userdict[user["id"]] = user
            user["highest_access_level"] = user["access_level"]
            userdict[user["id"]]["groups"] = [ [ path, user["access_level"], group_url, user["shared_from_group"] ] ]

def prepare_userdict(grouplist, projectlist):
    userdict = {}
    for group in grouplist:
        if "members" in group:
            group_path = group["full_path"]
            add_user(group["members"], group_path, userdict, group["web_url"])

    for project in projectlist:
        if "members" in project:
            project_path = project["path_with_namespace"]
            add_user(project["members"], project_path, userdict, project["web_url"])
    return userdict

def get_users_without_groups(api_url, userdict, page, failures):
    userdata = requests.get("%s/users?page=%s&per_page=%s" % (api_url, page, 100), headers=headers, verify=do_verify)
    if userdata:
        for user in userdata.json():
            has_group = False
            for group in userdict:
                # ugly af. The no query function loads from json and thus saves user ids as strings, however, crawling it directly stores ints
                if str(user["id"]) in userdict[group] or user["id"] in userdict[group] and group != "users without groups":
                    has_group = True
                    break
            if not has_group:
                # user is not one of the builtin bot users
                if user["name"] not in ["GitLab Support Bot", "GitLab Alert Bot", "Ghost User"]:
                    if str(user["id"]) not in userdict["users without groups"]:
                        user["groups"] = [["users without groups", None, "urn:no_group", None]]
                        user["access_level"] = None
                        user["highest_access_level"] = None
                        userdict["users without groups"][str(user["id"])] = user
        if len(userdata.json()) == per_page:
            page += 1
            print("Getting next page for users without groups" + str(page))
            get_users_without_groups(api_url, userdict, page, failures)
    else:
        failures["users without groups"].append("users without groups")
        print("Could not retrieve users without groups. Use an admin token", file=sys.stderr)

def get_additional_userdata(api_url, userdict):
    isAdmin = True
    for user in userdict.values():
        userdata = requests.get("%s/users/%s" % (api_url, user["id"]), headers=headers, verify=do_verify)
        if userdata:
            if "created_at" in userdata.json():
                user["has_private_profile"] = False
                user["created_at"] = userdata.json()["created_at"]
            else:
                user["has_private_profile"] = True
                user["created_at"] = "Profile is private"

            if isAdmin:
                #use last sign in as proxy to check if admin access has been set correctly
                if "last_sign_in_at" in userdata.json():
                    user["last_sign_in_at"] = userdata.json()["last_sign_in_at"]
                    user["last_activity_on"] = userdata.json()["last_activity_on"]
                    user["email"] = userdata.json()["email"]
                    user["state"] = userdata.json()["state"]
                else:
                    print("Cannot get additional user data. Use an admin token for additional user data.", file=sys.stderr)
                    isAdmin = False
        else:
            print("Could not retrieve user %s." % user["name"], file=sys.stderr)
    return isAdmin

def get_last_user_events(api_url, userdict):
    for user in userdict.values():
        userevents = requests.get("%s/users/%s/events" % (api_url, user["id"]), headers=headers, verify=do_verify)
        if userevents:
            # can't get this json: list index out of range
            try:
                user["last_activity_on"] = userevents.json()[0]["created_at"]
            except:
                user["last_activity_on"] = ""
                if user["has_private_profile"]:
                    user["last_activity_on"] = "Profile is private"
        else:
            print("API call to retrieve user %s failed. User activity will be incomplete." % user["name"], file=sys.stderr)
            user["last_activity_on"] = ""

def read_filterfile(filterfile):
    filterset = set()
    try:
        with open(filterfile,"r") as f_file:
            for line in f_file:
                filterset.add(line.strip().lower())
    except:
        print("Can not open file: " + filterfile)
    return filterset

def check_group_shares(api_url, top_group, group_grouplist, failures):
    # not resolving members in here for now, just flagging shares outside top namespace
    failures["shared_groups"] = []
    for group in group_grouplist:
        if len(group["shared_with_groups"])>0:
            for shared_group in group["shared_with_groups"]:
                if top_group not in shared_group["group_full_path"]:
                    print("Group %s is shared with Group %s, outside %s namespace. This may have imported additional users and may be a compliance issue." % (group["full_path"], shared_group["group_full_path"], top_group), file=sys.stderr)
                    failures["shared_groups"].append([group["full_path"], shared_group["group_full_path"]])

def produce_csvs(userdict, failurelist, requested_group, do_squash, reportdate):
    fields = ["id","username","name","main_group_access_level","highest_access_level","groups","last_activity_on","created_at"]
    if do_squash:
        #does not make sense if there is no main group
        fields.remove("main_group_access_level")
    admin_fields = ["email","last_sign_in_at","state"]
    if isAdmin:
        fields.extend(admin_fields)

    with open(requested_group + "_all_members_" + reportdate + ".csv","w") as complete_report:
        reportwriter = csv.writer(complete_report, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        if failurelist:
            failures = ", ".join(failurelist)
            reportwriter.writerow(["# Report incomplete, could not read group %s!" % failures])
        reportwriter.writerow(fields)
        for user in userdict.values():
            row = []
            for field in fields:
                if field == "groups":
                    groupstring = ""
                    for group in user["groups"]:
                        if group[1] is not None:
                            groupstring += "%s:%s " % (str(group[1]), group[0])
                        else:
                            groupstring += ""
                        if group[3] is not None:
                            groupstring += "(shared via %s), " % ( str(group[3][2]) )
                        else:
                            groupstring += ", "
                    row.append(groupstring[0:-2])
                elif field == "main_group_access_level":
                    is_top_member = False
                    for group in user["groups"]:
                        if group[0] == requested_group:
                            row.append(str(group[1]))
                            is_top_member = True
                    if not is_top_member:
                        row.append("0")
                else:
                    row.append(user[field])
            reportwriter.writerow(row)

parser = argparse.ArgumentParser(description='Create report for GitLab group members')
parser.add_argument('-u','--gitlaburl', default="https://gitlab.com/")
parser.add_argument('-g','--groups', nargs='+', help="Groups to report on, can provide multiple groups, whitespace separated.")
parser.add_argument('-c','--csv', help="Produce CSV files", action='store_true')
parser.add_argument('-q','--query', help="Query new, otherwise load JSONs and make html", action='store_true')
parser.add_argument('-f','--filterfile', help="Filepath to filter file. Format: one username per line. Filter file will filter users from results.")
parser.add_argument('-i','--instance', help="Provides a consolidated report for all groups in the instance.", action='store_true')
parser.add_argument('-s','--squash', help="Only provide one file instead of per group", action='store_true')
parser.add_argument('--nossl', help="Don't verify ssl", action='store_true')
# no ssl mode
args = parser.parse_args()

GITLAB = args.gitlaburl if args.gitlaburl.endswith("/") else args.gitlaburl + "/"
api_url = GITLAB + "api/v4"
headers = {'PRIVATE-TOKEN': os.environ["GIT_TOKEN"]}
do_instance = args.instance
do_verify = not(args.nossl)

if args.groups:
    if do_instance:
        print("Instance mode (-i) queries all groups and overrides group (-g) setting.")
    requested_groups = args.groups
else:
    requested_groups = []

filterfile = args.filterfile
do_csv = args.csv
query = args.query

reportdate = datetime.now().strftime('%Y-%m-%d')

do_squash = args.squash
per_page = 100
groupdict = {}
userdict = {}
failures = {}

if filterfile:
    filterset = read_filterfile(filterfile)

if query:
    if do_instance:
        requested_groups = get_top_groups(api_url, 1)

    for requested_group in requested_groups:
        print("Querying "+requested_group)
        top_group = requests.get("%s/groups/%s" % (api_url, requested_group), headers=headers, verify=do_verify)
        group_userdict = {}
        group_grouplist = []
        fail_list = []
        if top_group:
            group_grouplist.append(top_group.json())

            print("Retrieving subgroups")
            get_sub_groups(api_url, requested_group, 1, group_grouplist)
            print("Checking for group shares")
            check_group_shares(api_url, top_group.json()["path"], group_grouplist, failures)
            print("Retrieving projects")
            projectlist = get_projects(api_url, group_grouplist, 1, "false")
            print("Retrieving archived projects")
            projectlist.extend(get_projects(api_url, group_grouplist, 1, "true"))
            print("Found %s projects" % str(len(projectlist)))
            print("Retrieving group members")
            for group in group_grouplist:
                success = get_group_members(api_url, group, 1, "groups")
                if not success:
                    fail_list.append(group)
                time.sleep(0.5)

            print("Retrieving project members")
            for project in projectlist:
                success = get_group_members(api_url, project, 1, "projects")
                if not success:
                    fail_list.append(group)
                else:
                    if "failed_to_retrieve" in project:
                        fail_list.extend(project["failed_to_retrieve"])
                time.sleep(0.5)

            group_userdict = prepare_userdict(group_grouplist, projectlist)
            print("Trying to get additional user data")
            isAdmin = get_additional_userdata(api_url, group_userdict)
            if not isAdmin:
                print("Falling back to no-admin mode: Using user events as a proxy to last activity date. User events on private projects outside of your API token's visibility may be hidden.")
                get_last_user_events(api_url, group_userdict)
            failures[requested_group] = list(set(fail_list))
            userdict[requested_group] = group_userdict
            groupdict[requested_group] = group_grouplist
        else:
            print("Could not retrieve group %s. Use a group member token." % requested_group, file=sys.stderr)
    # get all users without a group
    if do_instance:
        userdict["users without groups"] = {}
        failures["users without groups"] = []
        get_users_without_groups(api_url, userdict, 1, failures)
else:
    try:
        with open("group_report.json","r") as report_file:
            groupdict = json.load(report_file)
    except:
        print("Could not open file: group_report.json")
    try:
        with open("failures.json","r") as report_file:
            failures = json.load(report_file)
    except:
        print("Could not open file: failures.json")
    try:
        with open("allusers_report.json","r") as report_file:
            userdict = json.load(report_file)
            if do_instance:
                userdict["users without groups"] = {}
                if "users without groups" not in failures:
                    failures["users without groups"] = []
                get_users_without_groups(api_url, userdict, 1, failures)
    except:
        print("Could not open file: allusers_report.json")
    for group in userdict:
        for user in userdict[group].values():
            if "state" in user:
                isAdmin = True
            else:
                isAdmin = False
            break
        break

# filter userdict
if filterfile:
    filtered_dict = {}
    for group in userdict.keys():
        filtered_dict[group] = {}
        for user in userdict[group].values():
            if user["username"].lower() not in filterset:
                filtered_dict[group][user["id"]] = user
    userdict = filtered_dict

if do_squash:
    squashed_userdict = {}
    squashed_userdict["All_groups"] = {}
    for group in userdict.keys():
        for user in userdict[group].values():
            if user["id"] in squashed_userdict["All_groups"]:
                # merge their groups
                newgroups = user["groups"]
                olduser = squashed_userdict["All_groups"][user["id"]]
                olduser["groups"].extend(newgroups)
                #print(str(user["id"]) + " already in dict")
            else:
                squashed_userdict["All_groups"][user["id"]] = user
    userdict = squashed_userdict
    squashed_failures = {"All_groups":[]}
    for group in failures:
        squashed_failures["All_groups"].extend(failures[group])
    failures = squashed_failures
    requested_groups = ["All_groups"]

if do_csv:
    print("Producing CSVs")
    if do_instance and not do_squash:
        requested_groups.append("users without groups")
    for requested_group in requested_groups:
        #try:
        produce_csvs(userdict[requested_group], failures[requested_group], requested_group, do_squash, reportdate)
        #except KeyError:
        #    print("Could not find group '%s' in existing data. Maybe you want to query fresh with '-q'?" % requested_group)

if query:
    print("Producing JSONs")
    with open("group_report.json","w") as report_file:
        json.dump(groupdict, report_file, indent=4)

    with open("allusers_report.json","w") as report_file:
       json.dump(userdict, report_file, indent=4)

    with open("failures.json","w") as report_file:
       json.dump(failures, report_file, indent=4)

mytemplate = Template(filename='template/index.html')
with open("public/index.html","w") as outfile:
    outfile.write(mytemplate.render(allmembers = userdict, gitlab = GITLAB, isAdmin = isAdmin, failures = failures, squash = do_squash, reportdate = reportdate))
