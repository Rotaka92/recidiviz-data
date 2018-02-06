# Recidiviz - a platform for tracking granular recidivism metrics in real time
# Copyright (C) 2018 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================


from google.appengine.ext import ndb
from models.record import Record


"""
UsNyRecord

Datastore model for historical violation records (e.g. 
ROBB. WPN-NOT DEADLY, 04/21/1995, sentence: 20mo). Multiple records may map
to one inmate.

See Record for pre-populated fields. UsNyRecord extends 
these by adding the following:
    - last_custody_date: (date) Most recent date inmate returned for this 
        sentence (may not be the initial custody date - e.g., if parole
        was violated, may be readmitted for remainder of prison term)
    - admission_type: (string) 'New commitment' is beginning to serve a term,
        other reasons are usually after term has started (e.g. parole issue)
    - county_of_commit: (string) County the inmate was convicted/committed in
    - custody_status: (string) Scraped string on custody status (more granular
        than just 'released' / 'not-released')
    - earliest_release_date: (date) Earliest date to be released based on 
        min_sentence. In certain circumstances, may be released before this.
    - earliest_release_type: (string) The reason for the earliest possible
        release date.
    - parole_hearing_date: (date) Date of next hearing before Parole Board 
    - parole_hearing_type: (string) Type of hearing for next PB appearance.
    - parole_elig_date: (date) Date inmate will be eligible for parole
    - cond_release_date: (date) Release date based on prison discretion for
        'good time off' based on behavior. Releases prisoner on parole, but
        bypasses PB review.
    - max_expir_date: (date) Date of release if no PB or conditional release,
        maximum obligation to the state.
    - max_expir_date_parole: (date) Last possible date of ongoing parole
        supervision. Doesn't apply to all inmates.
    - max_expir_date_superv: (date) Last possible date of post-release 
        supervision. Doesn't apply to all inmates.
    - parole_discharge_date: (date) Final date of parole supervision, based on
        the parole board's decision to end supervision before max expiration.
    (Note: for the three 'max...'s, the latest date is considered controlling -
    that is, the inmate will not get out before that last date.)

See 'DOCCS Data Definitions' for full descriptions:
http://www.doccs.ny.gov/univinq/fpmsdoc.htm

"""
class UsNyRecord(Record):
    last_custody_date = ndb.DateProperty()
    admission_type = ndb.StringProperty()
    county_of_commit = ndb.StringProperty()
    custody_status = ndb.StringProperty()
    earliest_release_date = ndb.DateProperty()
    earliest_release_type = ndb.StringProperty()
    parole_hearing_date = ndb.DateProperty()
    parole_hearing_type = ndb.StringProperty()
    parole_elig_date = ndb.DateProperty()
    cond_release_date = ndb.DateProperty()
    max_expir_date = ndb.DateProperty()
    max_expir_date_parole = ndb.DateProperty()
    max_expir_date_superv = ndb.DateProperty()
    parole_discharge_date = ndb.DateProperty()
    # To remove post-migration
    last_release_date = ndb.DateProperty()
    last_release_type = ndb.StringProperty()