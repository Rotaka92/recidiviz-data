# Copyright 2017 Andrew Corp <andrew@andrewland.co> 
# All rights reserved.


from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel


"""
DocketItem

Datastore model for a specific query that a scraper should run. This might be
one name in a set of names to search for, one inmate ID in a list of inmates
to snapshot, etc.

Fields:
    - created: (datetime) Creation date of the docket item
    - region: (string) Region code of the scraper this item is intended for 
    - scrape_type: (string) Type of query this item should be part of
    - content: (string) Payload of the item. Often the inmate ID, name, etc. 
"""
class DocketItem(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add=True)
    started = ndb.DateTimeProperty()
    region = ndb.StringProperty()
    scrape_type = ndb.StringProperty()
    content = ndb.StringProperty()
