#!/usr/bin/env python
"""
     Copyright (c) 2015 World Wide Technology, Inc.
     All rights reserved.

     Revision history:
     16 December 2015  |  1.0 - initial release
     19 December 2015  |  1.1 - refacted code to handle errors
     20 December 2015  |  1.2 - Tested and run pylint

"""

DOCUMENTATION = '''
---
module: 
author: Joel W. King, World Wide Technology
version_added: "1.2"
short_description: Create Spark rooms, adding users and post messages.
description:
    - Cisco Spark is a cloud service providing persistent room-based chat and collaboration. This module uses the REST API to 
    - automate creating rooms, adding users to rooms, and sending text message and files to the room.


options:
    room:
        description:
            - The Spark room 
        required: true

    token:
        description:
            - Spark access token 
        required: true

    text:
        description:
            - Text message to send to the room
        required: false

    file:
        description:
            - File to post to the room
        required: false

    members:
        description:
            - email address of a registered member to add to the room
        required: false

    debug:
        description:
            - debug switch
        required: false
'''

EXAMPLES = '''

     Login at dev-preview.ciscospark.com/index.html and click on your picture in the upper right to get a token.

         learninglabs.cisco.com
         www.webex.com/ciscospark
         dev-preview.ciscospark.com/getting-started.html


     ansible localhost -m spark_room -a 'members=joe.user@wwt.com "text="this is a posting from Ansible" room=foobar token="redacted"' 

     - name: Add members to a room
       spark_room:
         room: "{{spark_room}}"
         members: "{{item}}"
         token: "{{spark_token}}"
       with_items:
          - joel.king@wwt.com
          - foo.bar@wwt.com

     - name: Send message to spark room
       spark_room:
         text: "Send a message and optionally the values of variables to the room {{spark_room}}"
         filename: "https://twitter.com/joel_w_king"
         room: "{{spark_room}}"
         token: "{{spark_token}}"

      

'''

import json
import httplib
import requests

# ---------------------------------------------------------------------------
# Spark Connection Class
# ---------------------------------------------------------------------------
class Connection(object):
    """
      Connection class for Cisco Spark

    """
    def __init__(self, debug=False, token="redacted"):
        self.debug = debug
        self.token = "Bearer %s" % token
        self.HEADER = {"Content-Type": "application/json", "Authorization": "%s" % self.token}
        self.server = "https://api.ciscospark.com"
        self.rooms = None
        self.code = 0
        self.changed = False
        self.response = None
        return



    def get_changed_flag(self):
        """ Return the status of the changed flag """
        return self.changed



    def genericPOST(self, URI, body):
        """
            POST the URI and body to the server
        """
        URI = "%s%s" % (self.server, URI)
        try:
            r = requests.post(URI, data=json.dumps(body), headers=self.HEADER, verify=False)
        except requests.ConnectionError as e:
            return (False, e)
        try:
            self.response = json.loads(r.content)
        except ValueError as e:
            self.response = "ValueError: %s %s" % (r.status_code, httplib.responses[r.status_code])
        return (r.status_code, self.response)



    def list_rooms(self):
        """
            Attempt to get a list of the existing rooms
        """
        URI = "%s%s" % (self.server, "/hydra/api/v1/rooms")
        try:
            r = requests.get(URI, headers=self.HEADER, verify=False)
        except requests.ConnectionError as e:
            return (404, None)
        try:
            self.rooms = json.loads(r.content)["items"]
        except ValueError as e:
            self.rooms = None
        return (r.status_code, self.rooms)



    def get_room_id(self, title):
        """
            The roomId is a string hash value unique identifier of a room, different from the friendly name
        """
        if self.rooms:
            for rooms in self.rooms:
                if title in rooms["title"]:
                    return rooms["id"]
            return None
        return None


    def send_message(self, room_id, msg, filename):
        """
            Send a text message and/or file (or both) to the room
        """
        payload = {"roomId" : room_id}

        if msg:
            payload["text"] = msg
        if filename:
            payload["file"] = filename

        rc, self.response = self.genericPOST("/hydra/api/v1/messages", payload)

        return self.set_returncode(rc), self.response



    def create_room(self, title):
        """
            Create a spark room
        """
        body = {"title" : title}
        rc, self.response = self.genericPOST("/hydra/api/v1/rooms", body)
        if rc == 200:
            self.set_returncode(rc)
            return self.response["id"]
        else:
            return self.set_returncode(rc)



    def add_room_member(self, room_id, email):
        """
            Add a user to the room
        """
        body = {"personEmail" : email, "isModerator" : "false", "roomId" : room_id}
        rc, self.response = self.genericPOST("/hydra/api/v1/memberships", body)

        if rc == 403:                                      # User is already a participant
            return 403
        else:
            return self.set_returncode(rc)



    def set_returncode(self, rc):
        """
            Keep a running tally of non 200 return codes so we can determine how to exit
            Also set the changed flag. This routine should only be called by functions
            which POST to spark.
        """
        if rc == 200:
            self.changed = True
            return rc
        else:
            self.code = self.code + rc 
            return None

def main():
    "main"
    module = AnsibleModule(
        argument_spec=dict(
            room=dict(required=True),
            token=dict(required=True),
            text=dict(required=False),
            filename=dict(required=False),
            members=dict(required=False),
            debug=dict(required=False, default=False)
         ),
        check_invalid_arguments=False,
        add_file_common_args=True
    )

    room = module.params["room"]
    token = module.params["token"]
    text = module.params["text"]
    filename = module.params["filename"]
    members = module.params["members"]
    debug = module.params["debug"]

    spark = Connection(token=token, debug=debug)           # Create the connection object
    spark.list_rooms()                                     # Query Spark to get a list of existing rooms
    room_id = spark.get_room_id(room)                      # Get the hash which identifies the room

    if not room_id:
        room_id = spark.create_room(room)                  # Create room if it doesn't exist

    if members:
        spark.add_room_member(room_id, members)            # Add members (if any)

    if text or filename:
        spark.send_message(room_id, text, filename)        # Send a msg or file if provided

    if spark.code == 0:
        module.exit_json(changed=spark.get_changed_flag(), content=spark.response)
    else:
        module.fail_json(msg=spark.response)

    return spark.code

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
