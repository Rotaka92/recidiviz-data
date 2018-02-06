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


from datetime import datetime
import logging
import random
import string
import time

from env_vars import EnvironmentVariable
from us_ny.us_ny_inmate_snapshot import UsNyInmateSnapshot
from us_ny.us_ny_inmate import UsNyInmate
from us_ny.us_ny_record import UsNyRecord
from us_ny.us_ny_scrape_session import ScrapeSession, ScrapedRecord
from us_ny.us_ny_scraper import generate_id
from models.inmate_snapshot import InmateFacilitySnapshot
from models.query_docket import DocketItem
from models.record import SentenceDuration
import webapp2


"""
PopulateDb
Used to set up the local server environment for testing. Should never be 
deployed to production server.

To use locally, add the following to your app.yaml file and remove before 
checking in.

# TEST ONLY - DO NOT CHECK IN / DEPLOY TO PROD
- url: /populate_test_db
  script: scraper.populate_test_db.app
  login: admin
"""
class PopulateDb(webapp2.RequestHandler):

    def get(self):
        """
        get()
        Request handler to populate the db with relevant environment variables
        and test data.

        Example queries:
        Delete any existing datastore contents, populate environment variables and fake data in the datastore:
        http://localhost:8080/populate_test_db?rand_var=987123879812739871283&wipe_db=true

        Add more fake data to the datastore, but don't wipe what's already there:
        http://localhost:8080/populate_test_db?rand_var=987123879812739871283&env_only=true

        Populate environment variables only, and wipe anything else in the datastore:
        http://localhost:8080/populate_test_db?rand_var=987123879812739871283&wipe_db=true&env_only=true

        Args:
            rand_var: Must == 987123879812739871283, just in case does hit prod
            env_only: "true" or "false", whether to populate only the environment
                      variables (no fake data)

        Returns:
            HTTP 200 if successful 
            HTTP 400 if not
        """
        # Get and validate params
        rand_var = self.request.get('rand_var', None)
        env_only = self.request.get('env_only', "false").lower()
        wipe_db = self.request.get('wipe_db', "false").lower()

        env_only = True if env_only == "true" else False
        wipe_db = True if wipe_db == "true" else False

        if rand_var != "987123879812739871283":
            logging.error("Test datastore request missing safeguard 'rand_var',"
                          " exiting.")
            self.response.write("Invalid parameters, see logs.")
            self.response.set_status(500)
            return

        if wipe_db:
            logging.info("Wiping datastore...")
            purge_datastore()

        # Add environment variables - NOTE: These use the test username/pass, not the ones used in prod
        proxy_pass = EnvironmentVariable(
            name="proxy_password",
            region="all",
            value="v1sdfi24dvr1")

        proxy_user = EnvironmentVariable(
            name="proxy_user",
            region="all",
            value="lum-customer-hl_70604131-zone-zone_test")

        proxy_pass.put()
        proxy_user.put()


        if not env_only:
            # Add some sample NY inmates, records, and snapshots to work with
            # Sleeps allow datastore indices to catch up, since each method 
            # below relies on the prior's generated data
            logging.info("Generating fake data...")
            generate_inmates(5)
            time.sleep(5)
            generate_inmate_records(3)
            time.sleep(5)
            generate_inmate_snapshots(0)
            generate_old_snapshot_type(5)

            # Wrap up
            self.response.write("Database populated, feel free to test.")

        logging.info("Completed test datastore setup.")


def purge_datastore():
    """
    purge_datastore()

    Clears all existing entities from datastore

    Args:
        N/A

    Returns:
        Nothing
    """
    env_var_query = EnvironmentVariable.query().fetch()
    inmate_query = UsNyInmate.query().fetch()
    record_query = UsNyRecord.query().fetch()
    inmate_facility_snapshot_query = InmateFacilitySnapshot.query().fetch()
    inmate_snapshot_query = UsNyInmateSnapshot.query().fetch()
    scraped_session_query = ScrapeSession.query().fetch()
    scraped_record_query = ScrapedRecord.query().fetch()
    docket_item_query = DocketItem.query().fetch()

    for env_var in env_var_query:
        env_var.key.delete()

    for inmate in inmate_query:
        inmate.key.delete()

    for record in record_query:
        record.key.delete()

    for facility_snapshot in inmate_facility_snapshot_query:
        facility_snapshot.key.delete()

    for snapshot in inmate_snapshot_query:
        snapshot.key.delete()

    for session in scraped_session_query:
        session.key.delete()

    for scraped_record in scraped_record_query:
        scraped_record.key.delete()

    for docket_item in docket_item_query:
        docket_item.key.delete()


def generate_inmates(num_inmates):
    """
    Generates inmate entities with semi-random field values

    Args:
        num_inmates: How many to generate

    Returns:
        Nothing
    """
    for n in range(num_inmates):
        inmate_id = generate_id(UsNyInmate)
        inmate = UsNyInmate.get_or_insert(inmate_id)

        inmate.inmate_id = inmate_id
        inmate.us_ny_inmate_id = inmate_id
        inmate.inmate_id_is_fuzzy = True
        inmate.birthday = details_generator("datetime", True)
        inmate.age = details_generator("int", True)
        inmate.sex = details_generator("enum", True, ["male", "female"])
        inmate.race = details_generator("enum", True, ["black", "caucasian", "hispanic"])
        inmate.last_name = details_generator("string", False)
        inmate.given_names = details_generator("string", True)
        inmate.region = "us_ny"

        inmate_key = inmate.put()



def generate_inmate_records(num_records):
    """
    Generates inmate record entities with semi-random field values.

    Args:
        num_records: Generate up to this many records per inmate

    Returns:
        Nothing
    """
    inmate_query = UsNyInmate.query().fetch()

    for inmate in inmate_query:
        inmate_key = inmate.key

        for n in range(random.choice(range(0,num_records))):
            record_id = details_generator("string", False)
            record = UsNyRecord.get_or_insert(record_id, parent=inmate_key)

            record.last_custody_date = details_generator("datetime", False)
            record.admission_type = details_generator("enum", False, ["FROM PAROLE", "FIRST CUSTODY"])
            record.county_of_commit = details_generator("enum", False, ["Rockford", "Tallahassee", "Troubletown"])
            record.custody_status = details_generator("enum", False, ["IN CUSTODY", "WHO NOW?", "RELEASED TO PAROLE"])
            record.earliest_release_date = details_generator("datetime", True)
            record.earliest_release_type = details_generator("enum", True, ["Conditional", "Parole"])
            record.parole_hearing_date = details_generator("datetime", True)
            record.parole_hearing_type = details_generator("enum", True, ["Parole", "Conditional"])
            record.parole_elig_date = details_generator("datetime", True)
            record.cond_release_date = details_generator("datetime", True)
            record.max_expir_date = details_generator("datetime", True)
            record.max_expir_date_parole = details_generator("datetime", True)
            record.max_expir_date_superv = details_generator("datetime", True)
            record.parole_discharge_date = details_generator("datetime", True)

            if random.choice(range(10)) != 1:
                min_sentence_duration = SentenceDuration(
                    life_sentence=details_generator("bool", False),
                    years=details_generator("int", False),
                    months=details_generator("int", False),
                    days=details_generator("int", False))

                max_sentence_duration = SentenceDuration(
                    life_sentence=details_generator("bool", False),
                    years=details_generator("int", False),
                    months=details_generator("int", False),
                    days=details_generator("int", False))
            else:
                min_sentence_duration = None
                max_sentence_duration = None

            # General Record fields
            record.custody_date = details_generator("datetime", False)
            record.min_sentence_length = min_sentence_duration
            record.max_sentence_length = max_sentence_duration
            record.birthday = inmate.birthday
            record.sex = inmate.sex
            record.race = inmate.race
            record.last_release_type = details_generator("enum", True, ["Parole", "Conditional"])
            record.last_release_date = details_generator("datetime", True)
            record.last_name = inmate.last_name
            record.given_names = inmate.given_names
            record.record_id = record_id
            record.is_released = details_generator("bool", False)

            record_key = record.put()



def generate_inmate_snapshots(num_snapshots):
    """
    Generates inmate snapshot entities with semi-random field values

    Args:
        num_inmates: How many to generate up to per record

    Returns:
        Nothing
    """
    if num_snapshots:
        record_query = UsNyRecord.query().fetch()

        for record in record_query:

            for n in range(random.choice(range(1,num_snapshots))):
                record_key = record.key
                inmate_snapshot = UsNyInmateSnapshot(parent=record_key,
                                                     facility=details_generator("enum", False, ["Alcatraz", "Azkaban", "Mount Doom"]),
                                                     last_release_date=record.last_release_date,
                                                     last_release_type=record.last_release_type,
                                                     is_released=record.is_released,
                                                     min_sentence_length=record.min_sentence_length,
                                                     max_sentence_length=record.max_sentence_length,
                                                     last_custody_date=record.last_custody_date,
                                                     admission_type=record.admission_type,
                                                     county_of_commit=record.county_of_commit,
                                                     custody_status=record.custody_status,
                                                     earliest_release_date=record.earliest_release_date,
                                                     earliest_release_type=record.earliest_release_type,
                                                     parole_hearing_date=record.parole_hearing_date,
                                                     parole_hearing_type=record.parole_hearing_type,
                                                     parole_elig_date=record.parole_elig_date,
                                                     cond_release_date=record.cond_release_date,
                                                     max_expir_date=record.max_expir_date,
                                                     max_expir_date_superv=record.max_expir_date_superv,
                                                     max_expir_date_parole=record.max_expir_date_parole,
                                                     parole_discharge_date=record.parole_discharge_date)

                snapshot_key = inmate_snapshot.put()


def generate_old_snapshot_type(num_snapshots):
    """
    Generates inmate entities with semi-random field values

    Args:
        num_inmates: How many to generate up to per record

    Returns:
        Nothing
    """
    if num_snapshots:
        record_query = UsNyRecord.query().fetch()

        for record in record_query:

            for n in range(random.choice(range(1,num_snapshots))):
                record_key = record.key
                inmate_snapshot = InmateFacilitySnapshot(parent=record_key,
                                                     facility=details_generator("enum", False, ["Alcatraz", "Azkaban", "Mount Doom"]))

                snapshot_key = inmate_snapshot.put()


def details_generator(field_type, none_accepted, options=None):
    """
    Generates a field value for a particular field type.

    Args:
        field_type: Accepts 'enum', 'bool', 'datetime', 'int', and 'string'
        none_accepted: Whether this field will accept 'None'
        options: If enum, the options for it
    """
    if none_accepted:
        if random.choice(range(10)) == 3:
            return None

    if field_type == "enum":
        if options:
            # Get a random one of the options values
            return random.choice(options)
        else:
            raise Exception("populate_test_db/details_generator: No options "
                            "provided for enum.")
    elif field_type == "bool":
        # Randomly select True or False
        return random.choice([True, False])
    elif field_type == "datetime":
        # Generate a pseudo-random datetime
        year = random.randint(1950, 2010)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        return datetime(year, month, day)
    elif field_type == "string":
        # Generate a pseudo-random string less than 10 chars
        result_string = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(3,15)))
        return result_string.upper()
    elif field_type == "int":
        # Generate an integer less than 50
        return random.randint(1,50)
    else:
        raise Exception("populate_test_db/details_generator: Unrecognized field type.")


app = webapp2.WSGIApplication([
    ('/populate_test_db', PopulateDb)
], debug=False)
